"""Execute the existing CancerSignal orchestrator in an owned disposable PostgreSQL DB."""
import argparse
from contextlib import contextmanager
from datetime import date
import json
from pathlib import Path
import sys
from uuid import UUID,uuid4
from .real_cache import clinical_input,digest,load_cohort,backend_fingerprint,recommendation,RealModelError


@contextmanager
def disposable_database(backend, database_env_file=None):
    from sqlalchemy import create_engine,text
    from app.core.config import get_settings, Settings
    from alembic.config import Config
    from alembic import command
    url=(Settings(_env_file=database_env_file) if database_env_file else get_settings()).database_url
    name='cancersignal_sim_'+uuid4().hex[:16]
    admin=create_engine(url,isolation_level='AUTOCOMMIT',connect_args={'connect_timeout':5})
    engine=None;created=False
    try:
        with admin.connect() as conn:conn.execute(text(f'CREATE DATABASE "{name}"'))
        created=True
        engine=create_engine(url.set(database=name),connect_args={'options':'-c timezone=UTC','connect_timeout':5})
        config=Config(str(backend/'alembic.ini'));config.set_main_option('script_location',str(backend/'alembic'))
        with engine.begin() as conn:
            config.attributes['connection']=conn;command.upgrade(config,'heads')
        yield engine
    finally:
        if engine:engine.dispose()
        if created:
            with admin.connect() as conn:conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def infer(backend,cohort,cache,env_file,allow_live=False,workers=1,database_env_file=None):
    backend=Path(backend).resolve();sys.path.insert(0,str(backend))
    from sqlalchemy.orm import Session
    from app.models import Patient,Observation
    from app.schemas.records import PatientCreate,ObservationRead
    from app.schemas.analysis import AnalysisRequest
    from app.services.analysis_service import create_analysis
    from app.api.dependencies import build_extractor
    from app.reasoning.interfaces import AnalysisPipeline
    from app.reasoning.trigger_engine import evaluate_triggers
    from app.rag.retrieval import retrieve_context
    from app.db.seed_rules import seed_rules
    from app.extraction.providers import ProviderSettings,ChatCompletionsProvider
    from app.explanation.service import ExplanationEngine
    settings=ProviderSettings(_env_file=Path(env_file))
    producer={'kind':'cancersignal.create_analysis','extraction':ChatCompletionsProvider(settings).provenance.model_dump(mode='json'),
              'inference_settings':settings.model_dump(mode='json',exclude={'api_key'}),
              'retrieval':'app.rag.retrieval.retrieve_context: complete eligible history with lexical ranking; not hybrid RAG',
              'explanation':'existing deterministic ExplanationEngine (no separate explanation LLM call)',
              'mapping':'triggered AND requires_clinician_review; QCancer does not control routing'}
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    from app.extraction.prompt import SYSTEM_PROMPT
    from app.extraction.schema import output_schema
    (cache/'extraction_system_prompt.txt').write_text(SYSTEM_PROMPT)
    (cache/'extraction_output_schema.json').write_text(json.dumps(output_schema(),indent=2))
    manifest={'schema_version':'real-model-cache-1','pipeline_sha256':backend_fingerprint(backend),'producer':producer,'entries':{},'failures':[]}
    old_path=cache/'manifest.json'
    if old_path.exists():
        old=json.loads(old_path.read_text())
        if old['pipeline_sha256']!=manifest['pipeline_sha256'] or old['producer']!=producer:
            raise RealModelError('Cache producer/backend changed: use a new directory')
        manifest['entries'].update(old['entries'])
    # Actual analysis function commits only into this explicitly owned new database.
    with disposable_database(backend,database_env_file) as engine:
        with Session(engine) as session:
            seed_rules(session);session.commit()
        def run_case(case):
            extractor=build_extractor('llm',Path(env_file),allow_live,cache/'extraction_responses')
            captured={}
            class AuditedExtractor:
                name=extractor.name
                def extract(self,context,note):
                    from app.services.llm_extraction import to_contract_context
                    from app.extraction.prompt import messages
                    from app.contracts.clinical_context import SourceObservation
                    captured['retrieved_context']=context.model_dump(mode='json')
                    captured['llm_messages']=messages(to_contract_context(context,note.text or ''),SourceObservation.model_validate(note.model_dump()),None)
                    return extractor.extract(context,note)
            pipeline=AnalysisPipeline(retrieve=retrieve_context,extractor=AuditedExtractor(),evaluate=evaluate_triggers)
            entries=[];failures=[]
            with Session(engine) as session:
                for decision in case['decisions']:
                    payload=clinical_input(case,decision);input_hash=digest(payload)
                    key=case['patient']['id']+':'+decision['decision_id']
                    filename=digest({'input':input_hash,'pipeline':manifest['pipeline_sha256'],'producer':producer})+'.json'
                    if (cache/filename).exists():
                        from .real_cache import validate_entry
                        entry=json.loads((cache/filename).read_text());validate_entry(entry,case,decision,manifest)
                        entries.append((key,filename));continue
                    patient=PatientCreate.model_validate(payload['patient'])
                    if session.get(Patient,patient.id) is None:session.add(Patient(**patient.model_dump()))
                    session.flush()
                    for raw in payload['observations']:
                        row=ObservationRead.model_validate(raw)
                        old=session.get(Observation,row.id)
                        if old is None:session.add(Observation(**row.model_dump()))
                        elif ObservationRead.model_validate(old)!=row:raise RealModelError('Changed historical record across decisions')
                    session.commit()
                    response=create_analysis(session,patient.id,AnalysisRequest(note_observation_id=UUID(payload['input_note_id'])),pipeline)
                    raw=response.model_dump(mode='json')
                    if raw['status']!='completed':
                        failures.append({'patient_id':str(patient.id),'decision_id':decision['decision_id'],'error_code':raw['provenance']['error_code']})
                        (cache/(filename+'.failed.json')).write_text(json.dumps({'clinical_input':payload,'response':raw},indent=2,ensure_ascii=False))
                        continue
                    entry={'patient_id':str(patient.id),'decision_id':decision['decision_id'],'input_sha256':input_hash,
                        'pipeline_sha256':manifest['pipeline_sha256'],'producer':producer,'clinical_input':payload,
                        'response':raw,'response_sha256':digest(raw),'recommendation':recommendation(raw),'inference_audit':dict(captured)}
                    note=next(o for o in payload['observations'] if o['id']==payload['input_note_id'])
                    try:entry['explanation']=ExplanationEngine().explain_api(response,input_note=ObservationRead.model_validate(note)).model_dump(mode='json')
                    except ValueError:entry['explanation_unavailable']='Existing explanation adapter rejected the response; routing uses validated rule output only.'
                    (cache/filename).write_text(json.dumps(entry,indent=2,ensure_ascii=False,allow_nan=False))
                    entries.append((key,filename))
            return entries,failures
        if workers>1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as pool:results=list(pool.map(run_case,cohort))
        else:results=[run_case(case) for case in cohort]
        for entries,failures in results:
            manifest['entries'].update(entries);manifest['failures'].extend(failures)
    old_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False,allow_nan=False))
    print(json.dumps({'cached_decisions':len(manifest['entries']),'failures':manifest['failures'],'provider':settings.provider,'model':settings.model}))
    if manifest['failures']:raise RealModelError('Actual inference failed for some decisions; no fallback predictions were created')
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend',required=True);p.add_argument('--cohort',required=True);p.add_argument('--cache',required=True)
    p.add_argument('--database-env-file');p.add_argument('--env-file',required=True);p.add_argument('--allow-live',action='store_true');p.add_argument('--split',choices=['dev','test','all'],default='all');p.add_argument('--limit',type=int);p.add_argument('--workers',type=int,default=1)
    a=p.parse_args();cohort=load_cohort(a.cohort)
    if a.split!='all':cohort=[c for c in cohort if c['split']==a.split]
    if a.limit is not None:cohort=cohort[:a.limit]
    if not cohort:raise RealModelError('Empty cohort')
    infer(a.backend,cohort,a.cache,a.env_file,a.allow_live,a.workers,a.database_env_file)


if __name__=='__main__':main()
