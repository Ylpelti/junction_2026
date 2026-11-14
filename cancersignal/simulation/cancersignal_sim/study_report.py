"""Generate reviewable tables/plots from completed studies, without re-simulation."""
import argparse
import json
import os
from pathlib import Path
from .reporting import write_csv
from .study import estimate


def summarize(directory, destination=None):
    root=Path(directory)
    settings={p.stem:json.loads(p.read_text()) for p in root.glob('*.json') if p.stem!='manifest'}
    settings={k:v for k,v in settings.items() if 'summary' in v}
    def get(name,model,metric):
        return next(r for r in settings[name]['summary'] if r['model']==model and r['metric']==metric)
    def fmt(row,scale=1,difference=False):
        prefix='difference_' if difference else ''
        mean=row[prefix+'mean']; low=row[prefix+'ci95_low']; high=row[prefix+'ci95_high']
        if mean is None: return 'n/a'
        return f'{mean*scale:.2f}' + (f' [{low*scale:.2f}, {high*scale:.2f}]' if low is not None else '')
    lines=['# Models A–D: controlled comparison', '',
        'All parameters are hypothetical. All settings use 30 paired replications unless their exported valid-pair count states otherwise. Brackets are 95% paired Student-t Monte Carlo confidence intervals for changes, not clinical validation or parameter uncertainty. No multiple-comparison correction is applied.', '',
        'A = baseline; B = serial review; C = nonblocking review; D = selective review plus clinician-controlled repeat cancellation. Main settings use the same revised routing assumptions in all arms. The separate original-routing setting preserves the original behavior.', '',
        '## Main endpoints', '',
        'Cohort: identical arrivals from warmup through horizon−60, with a guaranteed 60-day observation window. Completion means the first investigation service has ended. Noncompletion contributes 60 days to capped time. Investigation counts include explicit repeats. Values are means of per-replication statistics.', '',
        '| GP slots / horizon | Model | Relevant completion by 60d (%) | Change vs A (percentage points, 95% CI) | Capped time (days) | Change vs A (days, 95% CI) | Other-patient tests per 1,000 other patients |',
        '| --- | --- | ---: | --- | ---: | --- | ---: |']
    for name in ('gp2_180','gp3_180','gp2_365','gp3_365'):
        if name not in settings: continue
        for model in 'ABCD':
            a=get(name,model,'cohort.relevant.completion_60_rate');b=get(name,model,'cohort.relevant.capped_completion_60_days');t=get(name,model,'cohort.other.investigations_per_1000')
            lines.append(f'| {name} | {model} | {100*a["mean"]:.2f} | {fmt(a,100,True)} | {b["mean"]:.2f} | {fmt(b,1,True)} | {t["mean"]:.2f} |')
    lines+=['','## Direct serial delay versus indirect queue effects','','Among relevant patients initially indicated by the GP and investigated in both arms, this table compares **post-GP** investigation delay against A. It separates serial review from changed initial GP queues; residual diagnostic contention can still change post-GP waiting. It is selected on both-arm observation.','','| Setting | B change in days | C change in days | D change in days |','| --- | --- | --- | --- |']
    for name in ('original_routing','gp2_180','gp3_180','gp2_365','gp3_365'):
        if name not in settings: continue
        lines.append('| '+name+' | '+' | '.join(fmt(get(name,m,'paired.relevant_initial_indicated.post_gp_difference_days'),difference=True) for m in 'BCD')+' |')
    lines+=['','The historical 9.37-day estimate used five seeds, investigation start and a selected observed subset. It is not numerically comparable to the new 30-seed fixed-window study. Legacy event-trace regression tests verify unchanged A/B behavior; the original-routing row isolates C’s workflow effect.','','## Complete workload, not just delivered work','','Closed 180-day arrivals are followed to day 1500. All arms must have zero unfinished patients in every replication. Service-days sum resource-specific effective service time; they are not interchangeable staffing costs.','','| Setting | Model | GP service-days / 1,000 arrivals | GP change vs A (95% CI) | Total service-days / 1,000 arrivals | Total change vs A (95% CI) |','| --- | --- | ---: | --- | ---: | --- |']
    for name in sorted(k for k in settings if k.startswith('drain_') or k=='closed_arrivals_drain'):
        for m in 'ABCD':
            incomplete=[r['metrics']['lifecycle.unfinished_n'] for r in settings[name]['replications'] if r['model']==m]
            if any(incomplete): raise ValueError(f'{name}/{m} has undrained workload')
            g=get(name,m,'lifecycle.gp_service_days_per_1000');t=get(name,m,'lifecycle.all_services_service_days_per_1000')
            lines.append(f'| {name} | {m} | {g["mean"]:.2f} | {fmt(g,difference=True)} | {t["mean"]:.2f} | {fmt(t,difference=True)} |')
    lines+=['','## Safety, unintended work and crowding','','Rates of longer waits compare each patient’s 60-day capped completion time with their own baseline. This counts queue spillover and routing effects. Zero measured repeat harm does not prove safety; the repeat-avoidability reference is itself hypothetical.','','| Setting / model | Relevant longer-wait fraction (%) | Lost relevant 60d completions (count) | Necessary repeats cancelled in relevant patients (count) | Mean GP queue | Queue growth / day |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name in ('gp2_180','gp3_180','gp2_365','gp3_365'):
        if name not in settings: continue
        for m in 'ABCD':
            keys=['paired.relevant.longer_wait_rate','paired.relevant.lost_completion60_n','cohort.relevant_necessary_repeat_cancelled_n','event.gp.mean_queue','event.gp.queue_growth_per_day']
            vals=[get(name,m,k)['mean'] for k in keys];vals[0]*=100
            lines.append(f'| {name}/{m} | '+' | '.join(f'{x:.3f}' for x in vals)+' |')
    lines+=['','## Selective workflow D versus C','','These are paired differences across the same seeds, not differences between independent confidence intervals.','','| Setting | Capped relevant time D−C (days, 95% CI) | Other-patient tests D−C per 1,000 (95% CI) | GP workload D−C per 1,000 arrivals (95% CI; complete lifecycle for drain) |','| --- | --- | --- | --- |']
    for name in ('gp2_180','gp3_180','gp2_365','gp3_365','closed_arrivals_drain'):
        if name not in settings: continue
        rr=settings[name]['replications'];cs={r['seed']:r['metrics'] for r in rr if r['model']=='C'}
        keys=['cohort.relevant.capped_completion_60_days','cohort.other.investigations_per_1000','lifecycle.gp_service_days_per_1000' if name=='closed_arrivals_drain' else 'cohort.all.gp_service_days_per_1000']
        cells=[]
        for key in keys:
            e=estimate([r['metrics'][key]-cs[r['seed']][key] for r in rr if r['model']=='D'])
            cells.append(fmt(e))
        lines.append('| '+name+' | '+' | '.join(cells)+' |')
    lines+=['','## Sensitivity summary','','All settings below change one parameter, hold the same 30 seeds, and retain the paired A–D populations. GP capacity is varied in the main grid and each sensitivity is repeated at capacities 2 and 3. Changes below are against A. CIs and every KPI are available in comparison.csv.','','| Setting | C capped-day change | D capped-day change | D other-test change / 1,000 |','| --- | ---: | ---: | ---: |']
    for name in sorted(k for k in settings if k.startswith(('gp2_','gp3_')) and k not in ('gp2_180','gp3_180','gp2_365','gp3_365')):
        vals=[get(name,'C','cohort.relevant.capped_completion_60_days')['difference_mean'],get(name,'D','cohort.relevant.capped_completion_60_days')['difference_mean'],get(name,'D','cohort.other.investigations_per_1000')['difference_mean']]
        lines.append('| '+name+' | '+' | '.join(f'{x:.2f}' for x in vals)+' |')
    lines+=['','## Boundaries','','The newer follow-up model changes baseline care as well as assisted care. Do not attribute the improvement relative to the old overloaded baseline entirely to AI. The common synthetic clinical-plan generator may use reference labels; intervention decisions see only its observable outputs and model signals. D’s selection is probabilistic, not a validated clinical prioritization model. First tests cannot be cancelled; false duplicate evidence can still cause incorrect repeat cancellations after paid clinician review.', '',
        'A growing GP queue with near-full utilization indicates finite-horizon overload; these are not steady-state estimates. Cohort workload is truncated at 60 days. Complete workload claims come only from the closed-arrival drain settings. Waiting-time percentiles are observed-only, while completion rates and capped times retain all eligible patients. The two horizons contain different arrival cohorts. No survival, stage-shift, cost-effectiveness or regional-equity claim is supported.']
    path=Path(destination) if destination else root/'COMPARISON_REPORT.md'
    path.write_text('\n'.join(lines)+'\n')
    write_csv(root/'comparison.csv',[{'experiment':name,**row} for name,r in settings.items() for row in r['summary']])
    # Rebuild manifest after any supplementary jobs; all configuration is in files.
    manifest=root/'manifest.json'
    metadata=json.loads(manifest.read_text()) if manifest.exists() else {}
    metadata.update(experiments=sorted(settings),replications_per_setting={n:len(r['configuration']['seeds']) for n,r in settings.items()})
    manifest.write_text(json.dumps(metadata,indent=2)+'\n')
    compact_keys = {
        'cohort.n','cohort.relevant_n','cohort.relevant.completion_30_rate','cohort.relevant.completion_60_rate',
        'cohort.relevant.capped_completion_60_days','cohort.relevant.never_started_60_rate',
        'cohort.relevant.gp_p50','cohort.relevant.gp_p90','cohort.relevant.gp_p95',
        'cohort.relevant.investigation_p50','cohort.relevant.investigation_p90','cohort.relevant.investigation_p95',
        'cohort.all.investigations_per_1000','cohort.other.investigations_per_1000',
        'cohort.review_service_days_per_1000','cohort.optimization_review_service_days_per_1000',
        'cohort.false_positive_review_n','cohort.false_negative_n','cohort.avoided_repeat_n',
        'cohort.correctly_avoided_repeat_n','cohort.relevant_necessary_repeat_cancelled_n',
        'paired.relevant.longer_wait_rate','paired.relevant.lost_completion60_n',
        'paired.relevant_initial_indicated.capped_mean_difference',
        'paired.relevant_initial_indicated.post_gp_difference_days',
        'event.gp.utilization','event.gp.mean_queue','event.gp.queue_growth_per_day',
        'event.diagnostic.utilization','event.specialist.utilization',
        'lifecycle.gp_service_days_per_1000','lifecycle.all_services_service_days_per_1000','lifecycle.unfinished_n',
    }
    compact=path.parent/'results';compact.mkdir(parents=True,exist_ok=True)
    write_csv(compact/'workflow_summary.csv',[{'experiment':name,**row} for name,r in settings.items() for row in r['summary'] if row['metric'] in compact_keys])
    (compact/'workflow_configurations.json').write_text(json.dumps({name:{'configuration':r['configuration'],'arrival_duration':r['arrival_duration']} for name,r in settings.items()},indent=2)+'\n')
    (compact/'README.md').write_text("# Workflow study artifacts\n\nworkflow_summary.csv contains selected means, paired changes versus A, 95% Monte Carlo intervals and valid-pair counts. workflow_configurations.json contains exact configurations. All parameters are hypothetical. Lifecycle workload is complete only in closed_arrivals_drain and drain_* settings; other lifecycle rows are horizon-truncated. See WORKFLOW_FINDINGS.md and WORKFLOW_COMPARISON.md for interpretation. Full per-seed metrics and sample event traces are in outputs/workflow_study.\n")
    plots(root,settings,get)
    return path


def plots(root,settings,get):
    os.environ.setdefault('MPLCONFIGDIR',str(root.resolve()/'.matplotlib'))
    os.environ.setdefault('XDG_CACHE_HOME',str(root.resolve()/'.cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names=['gp2_180','gp3_180','gp2_365','gp3_365']
    colors={'B':'#b66b45','C':'#16817c','D':'#7259a8'}
    fig,axes=plt.subplots(2,2,figsize=(13,9))
    for model,offset in [('B',-.2),('C',0),('D',.2)]:
        for ax,key,scale in [(axes[0,0],'cohort.relevant.capped_completion_60_days',1),(axes[0,1],'cohort.relevant.completion_60_rate',100),(axes[1,0],'cohort.other.investigations_per_1000',1)]:
            rows=[get(n,model,key) for n in names]
            ys=[r['difference_mean']*scale for r in rows]
            err=[(r['difference_ci95_high']-r['difference_mean'])*scale for r in rows]
            ax.errorbar([i+offset for i in range(4)],ys,yerr=err,fmt='o',capsize=3,label=model,color=colors[model])
            ax.set_xticks(range(4),['2 GP / 180d','3 GP / 180d','2 GP / 365d','3 GP / 365d'])
            ax.axhline(0,color='gray',lw=1)
    axes[0,0].set(title='Relevant capped time: change versus A',ylabel='Days (negative is faster)')
    axes[0,1].set(title='Relevant 60-day completion: change versus A',ylabel='Percentage points')
    axes[1,0].set(title='Other-patient investigations: change versus A',ylabel='Tests per 1,000 other patients')
    if 'closed_arrivals_drain' in settings:
        for i,m in enumerate('BCD'):
            r=get('closed_arrivals_drain',m,'lifecycle.all_services_service_days_per_1000')
            axes[1,1].errorbar(i,r['difference_mean'],yerr=r['difference_ci95_high']-r['difference_mean'],fmt='o',capsize=4,color=colors[m])
        axes[1,1].set_xticks(range(3),['B serial','C nonblocking','D selective'])
        axes[1,1].axhline(0,color='gray',lw=1)
        axes[1,1].set(title='Complete workload: change versus A',ylabel='Total service-days per 1,000 arrivals')
    axes[0,0].legend(title='Workflow')
    fig.suptitle('Hypothetical pathways: 30 paired replications; 95% Monte Carlo intervals')
    fig.tight_layout();fig.savefig(root/'workflow_comparison.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='outputs/workflow_study')
    parser.add_argument('--out')
    args=parser.parse_args()
    print(summarize(args.input,args.out))
