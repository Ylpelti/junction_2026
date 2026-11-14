"""Replay authentic CancerSignal decisions alongside an explicitly hypothetical benchmark."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from .inputs import Patient
from .engine import simulate
from .study import kpis,patient_comparison,aggregate
from .reporting import write_csv
from .real_cache import CachedRealSignals,RealModelError,load_cohort,digest


def load_labels(path):
    rows=json.loads(Path(path).read_text());labels={}
    for row in rows:
        if row['patient_id'] in labels or type(row.get('relevant')) is not bool or not row.get('label_source'):
            raise RealModelError('Labels must be separately sourced booleans with unique patient IDs')
        labels[row['patient_id']]=row
    return labels


def evaluate(cohort,labels,signals):
    outputs={}
    for split in ['all','dev','test']:
        cases=[c for c in cohort if split=='all' or c['split']==split]
        tp=fp=tn=fn=0;unlabeled=0;unavailable=[];risks=Counter();actions=Counter();missed=[];detail=[]
        for case in cases:
            pid=case['patient']['id'];label=labels.get(pid)
            if pid+':initial' not in signals.entries:
                unavailable.append({'patient_id':pid,'case_id':case['case_id'],'reference_relevant':label['relevant'] if label else None})
                continue
            entry=signals.entries[pid+':initial'];pred=entry['recommendation']
            risks[pred['urgency']]+=1;actions.update(pred['recommended_actions'])
            if label is None:unlabeled+=1;continue
            actual=pred['review_signal'];truth=label['relevant']
            tp+=truth and actual;fp+=not truth and actual;tn+=not truth and not actual;fn+=truth and not actual
            if truth and not actual:missed.append(pid)
            detail.append({'patient_id':pid,'case_id':case['case_id'],'reference_relevant':truth,'predicted_review':actual,
                           'urgency':pred['urgency'],'recommended_actions':pred['recommended_actions']})
        divide=lambda a,b:a/b if b else None
        outputs[split]={'n':len(cases),'labeled_n':tp+fp+tn+fn,'unlabeled_n':unlabeled,'unavailable':unavailable,'prediction_coverage':divide(len(cases)-len(unavailable),len(cases)),
                        'end_to_end_positive_review_yield':divide(tp,tp+fn+sum(x['reference_relevant'] is True for x in unavailable)),'confusion_matrix':{'tp':tp,'fp':fp,'tn':tn,'fn':fn},
                        'true_positive_rate':divide(tp,tp+fn),'false_positive_rate':divide(fp,fp+tn),'precision':divide(tp,tp+fp),'recall':divide(tp,tp+fn),
                        'missed_relevant_patient_ids':missed,'review_recommendations_by_urgency':dict(risks),
                        'recommended_action_counts':dict(actions),'patients':detail}
    return {'evaluation_scope':'Separately authored, rulebook-aligned synthetic labels; not independent clinical diagnostic validation. No labels/coded extraction answers entered inference.',
            'positive_endpoint':'Rule-based physician review recommendation, not a diagnosis or numerical risk threshold.',
            'denominators':'Model evaluation counts fixed patients once; 30 simulation replications do not enlarge this evaluation sample.',
            'splits':outputs}


def replay(config,cohort,labels,provider,out,backend=None,evaluation_cohort=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    patients=[]
    for case in cohort:
        label=labels.get(case['patient']['id'])
        patients.append(Patient(case['patient']['id'],case['arrival'],label['relevant'] if label else None,
            label['label_source'] if label else None,cohort=case['split'],as_of=case['decisions'][0]['as_of']))
    rows=[];traces={}
    # Entire fixed cohort must have complete follow-up, not only observed outcomes.
    if any(p.arrival<config['warmup'] or p.arrival>=config['duration']-60 for p in patients):
        raise RealModelError('Every integrated cohort arrival must have a guaranteed post-warmup 60-day observation window')
    for mode in ['real_model','hypothetical']:
        c=deepcopy(config);c['signal_mode']=mode
        c['workflow']['repeat_probability']=0
        for label in ('relevant','other','unknown'):c['workflow']['change_probability_'+label]=0
        # Model D has no fabricated duplicate optimization in either comparison.
        c['workflow']['duplicate_flag_tpr']=0;c['workflow']['duplicate_flag_fpr']=0
        records=[]
        for seed in c['seeds']:
            a=None
            for model in 'ACD':
                run=simulate(c,patients,seed,model=model,signals=provider if mode=='real_model' else None)
                if model=='A':a=run
                m=kpis(run,c);m.update({'paired.'+key:value for key,value in patient_comparison(a,run,c).items()})
                records.append({'model':model,'seed':seed,'metrics':m})
                if seed==c['seeds'][0]:
                    traces[mode+'_'+model]=run
                    (out/f'{mode}_{model}_first_run.json').write_text(json.dumps(run,indent=2,allow_nan=False))
        report={'mode':mode,'configuration':c,'patients':len(patients),'replications':records,'summary':aggregate(records),
                'cache_pipeline_sha256':provider.manifest['pipeline_sha256'] if mode=='real_model' else None,
                'cache_validation':provider.validation if mode=='real_model' else None,
                'prediction_source':'actual cached CancerSignal' if mode=='real_model' else 'hypothetical TPR/FPR benchmark; not measured model performance',
                'operational_assumptions':'Clinical routing, service times, review/escalation policies and capacities remain hypothetical. Fixed small cohort, no replication of records to claim population coverage.'}
        (out/(mode+'_results.json')).write_text(json.dumps(report,indent=2,allow_nan=False))
        rows.extend({'mode':mode,**r} for r in report['summary'])
    write_csv(out/'comparison.csv',rows)
    evaluation=evaluate(evaluation_cohort or cohort,labels,provider)
    (out/'model_evaluation.json').write_text(json.dumps(evaluation,indent=2,ensure_ascii=False,allow_nan=False))
    # Select an actual observed example where review changes routing; no manufactured trace.
    aa={p['patient_id']:p for p in traces['real_model_A']['patients']}
    cc={p['patient_id']:p for p in traces['real_model_C']['patients']}
    chosen=next((pid for pid,p in cc.items() if p['signal'] and 'review_start' in p and p['escalated']),patients[0].patient_id)
    case=next(c for c in cohort if c['patient']['id']==chosen)
    detailed={'patient':case,'reference_label_separate_from_input':labels.get(chosen),
        'actual_inference':provider.entries[chosen+':initial'],'pathways':{m:{'patient':next(p for p in traces['real_model_'+m]['patients'] if p['patient_id']==chosen),
        'events':[e for e in traces['real_model_'+m]['events'] if e['patient_id']==chosen]} for m in 'ACD'}}
    (out/'patient_trace.json').write_text(json.dumps(detailed,indent=2,ensure_ascii=False,allow_nan=False))
    return evaluation,rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort',required=True);p.add_argument('--labels',required=True);p.add_argument('--cache',required=True)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--backend',help='Verify current source against cached pipeline fingerprint')
    source.add_argument('--expected-pipeline-sha256',help='Explicit historical replay pin; does not claim predictions came from the current backend')
    p.add_argument('--config',default='config/real_model.json');p.add_argument('--out',default='outputs/real_model/study')
    p.add_argument('--split',choices=['dev','test','all'],default='all');p.add_argument('--evaluation-cohort',help='Original complete cohort for reporting prediction failures/coverage; never imputed')
    a=p.parse_args();cohort=load_cohort(a.cohort)
    if a.split!='all':cohort=[c for c in cohort if c['split']==a.split]
    if not cohort:raise RealModelError('Empty real-model cohort')
    provider=CachedRealSignals(cohort,a.cache,backend=a.backend,expected_pipeline_sha256=a.expected_pipeline_sha256)
    evaluation_cohort=load_cohort(a.evaluation_cohort) if a.evaluation_cohort else None
    if evaluation_cohort is not None and a.split!='all':
        evaluation_cohort=[c for c in evaluation_cohort if c['split']==a.split]
    evaluation,_=replay(json.loads(Path(a.config).read_text()),cohort,load_labels(a.labels),provider,a.out,evaluation_cohort=evaluation_cohort)
    print(json.dumps({k:{'n':v['n'],'confusion_matrix':v['confusion_matrix']} for k,v in evaluation['splits'].items()}))


if __name__=='__main__':main()
