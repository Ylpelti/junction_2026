"""Paired review-priority/capacity experiment; no selection based on favorable results."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from .study import run_setting

HEADLINES = [
    ('Relevant cohort size','cohort.relevant_n'),
    ('Investigations completed within 30 days (patients)','cohort.relevant.completion_30_n'),
    ('Investigations completed within 60 days (patients)','cohort.relevant.completion_60_n'),
    ('60-day completion fraction','cohort.relevant.completion_60_rate'),
    ('Gained 60-day completions versus A','paired.relevant.gained_completion60_n'),
    ('Lost 60-day completions versus A','paired.relevant.lost_completion60_n'),
    ('No completed investigation at 30 days (fraction)','cohort.relevant.without_completion_30_rate'),
    ('Capped 60-day completion P90 (days)','cohort.relevant.capped_completion_60_p90'),
    ('Observed completion P90 (days; completers only)','cohort.relevant.completion_p90'),
    ('GP utilization (fraction)','event.gp.utilization'),
    ('GP queue growth per day','event.gp.queue_growth_per_day'),
    ('Mean GP queue length','event.gp.mean_queue'),
    ('All-patient GP P90 (days; observed)','cohort.all.gp_p90'),
    ('Reference-negative investigations per 1,000','cohort.other.investigations_per_1000'),
]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default='config/demo.json');p.add_argument('--out',default='outputs/pitch_review')
    a=p.parse_args();base=json.loads(Path(a.config).read_text());base['seeds']=list(range(1001,1031))
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    text=['# Priority and capacity comparison','',
      'All operational parameters and signals in this population stress experiment are hypothetical. The separate real-model replay retains authentic predictions. Relevant is an assumed need for investigation, not confirmed cancer. Thirty paired replications per setting; identical arrivals, random streams and capacity across arms. All four settings are reported.','',
      'A: standard care. B: historical serial review. C: nonblocking review. D is also exported, but has the same selection behavior as C when the legacy configuration has no workflow block. Priority consumes the same GP capacity, does not interrupt active work, and can delay ordinary visits. Hypothetical signals have no actual urgency category.','',
      'Primary outcomes count first investigation completions with full 60-day observation, not all tests or selected completers. P90 is a time quantile, not a fraction; the fraction still waiting at 30 days is reported separately. Capped P90 counts noncompletion as 60 days.']
    for gp in [2,3]:
        for policy in ['fifo','priority']:
            c=deepcopy(base);c['capacities']['gp']=gp;c['review_queue']=policy
            name=f'gp{gp}_{policy}';run_setting(c,name,out,capture=True)
            r=json.loads((out/f'{name}.json').read_text())
            def get(m,k):return next(x['mean'] for x in r['summary'] if x['model']==m and x['metric']==k)
            text.extend(['',f'## GP capacity {gp}, {policy}','','| Endpoint | A | B | C |','|---|---:|---:|---:|'])
            for label,k in HEADLINES:
                values=[get(m,k) for m in 'ABC']
                text.append('| '+label+' | '+' | '.join('—' if v is None else f'{v:.3f}' for v in values)+' |')
            x=next(x for x in r['summary'] if x['model']=='C' and x['metric']=='cohort.relevant.completion_60_rate')
            text.extend(['',f"C−A 60-day completion difference: {100*x['difference_mean']:.2f} percentage points; paired 95% Monte Carlo interval [{100*x['difference_ci95_low']:.2f}, {100*x['difference_ci95_high']:.2f}]. This is not clinical confidence or parameter uncertainty."])
    (out/'REPORT.md').write_text('\n'.join(text)+'\n')

if __name__=='__main__':main()
