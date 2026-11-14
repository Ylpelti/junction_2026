"""Explicitly export a complete-prediction subset, retaining every exclusion.

This is separate from strict replay: real_study never silently drops a patient.
Use --evaluation-cohort to retain the original inference denominator in evaluation.
"""
import argparse,json
from pathlib import Path
from .real_cache import CachedRealSignals,load_cohort,RealModelError,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort',required=True);p.add_argument('--cache',required=True);p.add_argument('--backend',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();cases=load_cohort(a.cohort);selected=[];excluded=[]
    for case in cases:
        try:CachedRealSignals([case],a.cache,backend=a.backend)
        except RealModelError as e:excluded.append({'patient_id':case['patient']['id'],'case_id':case['case_id'],'reason':str(e)})
        else:selected.append(case)
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(selected,indent=2,ensure_ascii=False)+'\n')
    report={'original_cohort_sha256':digest(cases),'selected_cohort_sha256':digest(selected),'planned_n':len(cases),'validated_n':len(selected),
            'excluded':excluded,'warning':'Nonrandom inference failure may bias simulated outcomes. Failed cases are unavailable, never negative predictions. This is not a complete-cohort effectiveness estimate.'}
    dest.with_suffix('.selection.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
