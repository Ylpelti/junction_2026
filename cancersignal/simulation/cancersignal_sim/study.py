"""Four-arm paired study: fixed 60-day cohorts, events, uncertainty and safety."""
from copy import deepcopy
import json
import math
from pathlib import Path
import statistics as st
from .engine import simulate, validate
from .inputs import generate
from .reporting import distribution, quantile, write_csv

MODELS = ("A", "B", "C", "D")
GP_STAGES = ("gp", "review", "gp_followup", "gp_change", "optimization_review", "review_followup", "review_symptom_change")
SERVICE_STAGES = (*GP_STAGES, "nurse", "diagnostic", "diagnostic_repeat", "specialist")
WINDOW = 60


def average(values):
    return st.mean(values) if values else None


def fraction(n, d):
    return n / d if d else None


def spent(p, stage, stop, start=0):
    if stage + "_start" not in p:
        return 0.
    return max(0., min(p.get(stage + "_end", stop), stop) - max(p[stage + "_start"], start))


def reached(p, key, window=WINDOW):
    return key in p and p[key] - p['arrival'] <= window


def capped(p, key, window=WINDOW):
    return min(window, p.get(key, p['arrival'] + window) - p['arrival'])


def kpis(run, config):
    """Cohort metrics use a common [warmup, duration-60) arrival interval.

    Completion endpoints use diagnostic_end, not diagnostic_start. All patients
    in the denominator have 60 observable days; nonrouting remains a non-event.
    """
    lo, hi = config['warmup'], config['duration']
    patients = [p for p in run['patients'] if lo <= p['arrival'] < hi - WINDOW]
    rel = [p for p in patients if p['relevant'] is True]
    other = [p for p in patients if p['relevant'] is False]
    m = {'cohort.n': len(patients), 'cohort.relevant_n': len(rel), 'cohort.other_n': len(other)}
    for group, pp in [('all', patients), ('relevant', rel), ('other', other)]:
        n = len(pp)
        prefix = 'cohort.' + group + '.'
        for label, key in [('gp', 'gp_start'), ('investigation', 'diagnostic_start'), ('completion', 'diagnostic_end')]:
            times = [p[key]-p['arrival'] for p in pp if reached(p,key)]
            for stat, q in [('p50',.5), ('p90',.9), ('p95',.95)]:
                m[prefix+label+'_'+stat] = quantile(times,q)
            m[prefix+label+'_observed_n'] = len(times)
        for window in (30,60):
            count = sum(reached(p,'diagnostic_end',window) for p in pp)
            m[prefix+f'completion_{window}_rate'] = fraction(count,n)
            m[prefix+f'completion_{window}_n'] = count
        m[prefix+'never_started_60_rate'] = fraction(sum(not reached(p,'diagnostic_start') for p in pp),n)
        m[prefix+'never_completed_60_n'] = sum(not reached(p,'diagnostic_end') for p in pp)
        m[prefix+'never_completed_60_rate'] = fraction(m[prefix+'never_completed_60_n'],n)
        m[prefix+'capped_completion_60_p90'] = quantile([capped(p,'diagnostic_end') for p in pp], .9)
        m[prefix+'without_completion_30_rate'] = fraction(sum(not reached(p,'diagnostic_end',30) for p in pp),n)
        m[prefix+'capped_completion_60_days'] = average([capped(p,'diagnostic_end') for p in pp])
        m[prefix+'unfinished_pathway_60_rate'] = fraction(sum(p.get('pathway_exit',hi+1) > p['arrival']+WINDOW for p in pp),n)
        tests = sum(reached(p,s+'_end') for p in pp for s in ('diagnostic','diagnostic_repeat'))
        m[prefix+'investigations_per_1000'] = fraction(tests*1000,n)
        m[prefix+'investigations_n'] = tests
        for resource, stages in [('gp',GP_STAGES),('diagnostic',('diagnostic','diagnostic_repeat')),('all_services',SERVICE_STAGES)]:
            work = sum(spent(p,s,p['arrival']+WINDOW) for p in pp for s in stages)
            m[prefix+resource+'_service_days_per_1000'] = fraction(work*1000,n)
    for label,q in [('p50',.5),('p90',.9),('p95',.95)]:
        m['cohort.indication_to_investigation_'+label] = quantile([p['diagnostic_start']-p['first_indication'] for p in patients if reached(p,'diagnostic_start')],q)
    for name, condition in [
        ('review_started', lambda p: reached(p,'review_start')),
        ('false_positive_review', lambda p: p['relevant'] is False and reached(p,'review_start')),
        ('false_negative', lambda p: p['relevant'] is True and p['signal'] is False and reached(p,'signal_time')),
        ('signal_unavailable', lambda p: p['signal'] is None or not reached(p,'signal_time')),
        ('avoided_repeat', lambda p: p['repeat_avoided'] and reached(p,'optimization_review_end')),
        ('correctly_avoided_repeat', lambda p: p['repeat_avoided'] and p['repeat_avoidable_reference'] and reached(p,'optimization_review_end')),
        ('incorrectly_cancelled_repeat', lambda p: p['repeat_avoided'] and not p['repeat_avoidable_reference'] and reached(p,'optimization_review_end')),
        ('relevant_necessary_repeat_cancelled', lambda p: p['relevant'] is True and p['repeat_avoided'] and not p['repeat_avoidable_reference'] and reached(p,'optimization_review_end')),
        ('relevant_selective_review_skipped', lambda p: p['relevant'] is True and p['selective_review_skipped'] and reached(p,'selective_skip_time')),
    ]:
        m['cohort.'+name+'_n'] = sum(condition(p) for p in patients)
    for name, pp, stages in [('review',patients,('review',)),('optimization_review',patients,('optimization_review',)),('false_positive_review',other,('review',))]:
        m['cohort.'+name+'_service_days_per_1000'] = fraction(1000*sum(spent(p,s,p['arrival']+WINDOW) for p in pp for s in stages),len(patients))
    # Event-based resource accounting: all patients contribute, even pre-warmup.
    resources = run['resource_states']
    by_resource = {name: [] for name in config['capacities']}
    for state in resources:
        by_resource[state['resource']].append(state)
    for name, states in by_resource.items():
        busy=queue=0.
        start_state=states[0]
        for a,b in zip(states,states[1:]):
            if a['time'] <= lo: start_state=a
            dt=max(0,min(b['time'],hi)-max(a['time'],lo))
            busy+=a['busy']*dt
            queue+=a['queue']*dt
        m[f'event.{name}.utilization']=busy/((hi-lo)*config['capacities'][name])
        m[f'event.{name}.mean_queue']=queue/(hi-lo)
        m[f'event.{name}.queue_end']=states[-1]['queue']
        m[f'event.{name}.queue_growth_per_day']=(states[-1]['queue']-start_state['queue'])/(hi-lo)
    m['event.gp_review_service_days']=sum(spent(p,s,hi,lo) for p in run['patients'] for s in ('review','optimization_review'))
    # Lifecycle accounting is used only for explicitly closed-arrival drain runs.
    m['lifecycle.unfinished_n']=sum(not p['complete'] for p in run['patients'])
    for name,stages in [('gp',GP_STAGES),('diagnostic',('diagnostic','diagnostic_repeat')),('all_services',SERVICE_STAGES)]:
        m[f'lifecycle.{name}_service_days_per_1000']=fraction(1000*sum(spent(p,s,hi) for p in run['patients'] for s in stages),len(run['patients']))
    return m


def patient_comparison(baseline, run, config):
    aa={p['patient_id']:p for p in baseline['patients'] if config['warmup'] <= p['arrival'] < config['duration']-WINDOW}
    bb={p['patient_id']:p for p in run['patients']}
    result={}
    for name,ids in [('relevant',[i for i,p in aa.items() if p['relevant'] is True]),
                     ('initial_indicated',[i for i,p in aa.items() if p['baseline_initial_investigation']]),
                     ('relevant_initial_indicated',[i for i,p in aa.items() if p['relevant'] is True and p['baseline_initial_investigation']])]:
        ds=[capped(bb[i],'diagnostic_end')-capped(aa[i],'diagnostic_end') for i in ids]
        result[name+'.n']=len(ids)
        result[name+'.lost_completion60_n']=sum(reached(aa[i],'diagnostic_end') and not reached(bb[i],'diagnostic_end') for i in ids)
        result[name+'.gained_completion60_n']=sum(not reached(aa[i],'diagnostic_end') and reached(bb[i],'diagnostic_end') for i in ids)
        result[name+'.capped_mean_difference']=average(ds)
        result[name+'.longer_wait_rate']=fraction(sum(d>1e-9 for d in ds),len(ds))
        result[name+'.shorter_wait_rate']=fraction(sum(d < -1e-9 for d in ds),len(ds))
        for label,q in [('p50',.5),('p90',.9),('p95',.95)]: result[name+'.individual_difference_'+label]=quantile(ds,q)
        # Additional post-GP delay separates direct review delay from shared queues.
        both=[i for i in ids if reached(aa[i],'diagnostic_start') and reached(bb[i],'diagnostic_start')]
        result[name+'.both_observed_n']=len(both)
        result[name+'.post_gp_difference_days']=average([(bb[i]['diagnostic_start']-bb[i]['gp_end'])-(aa[i]['diagnostic_start']-aa[i]['gp_end']) for i in both])
    return result


# Two-sided 95% Student-t quantiles, df=1..30; higher df uses a convergent
# asymptotic quantile expansion. These are Monte Carlo intervals, not clinical CIs.
T95=[12.7062,4.3027,3.1824,2.7764,2.5706,2.4469,2.3646,2.3060,2.2622,2.2281,2.2010,2.1788,2.1604,2.1448,2.1314,2.1199,2.1098,2.1009,2.0930,2.0860,2.0796,2.0739,2.0687,2.0639,2.0595,2.0555,2.0518,2.0484,2.0452,2.0423]


def estimate(values):
    v=[x for x in values if x is not None]
    n=len(v)
    if not n: return {'n':0,'mean':None,'ci95_low':None,'ci95_high':None}
    avg=st.mean(v)
    if n<2: return {'n':n,'mean':avg,'ci95_low':None,'ci95_high':None}
    df=n-1; z=1.959963984540054
    t=T95[df-1] if df<=30 else z+(z**3+z)/(4*df)+(5*z**5+16*z**3+3*z)/(96*df**2)+(3*z**7+19*z**5+17*z**3-15*z)/(384*df**3)
    se=st.stdev(v)/math.sqrt(n)
    return {'n':n,'mean':avg,'sd':st.stdev(v),'mc_se':se,'ci95_low':avg-t*se,'ci95_high':avg+t*se}


def aggregate(records):
    rows=[]
    baselines={r['seed']:r for r in records if r['model']=='A'}
    for model in MODELS:
        rr=[r for r in records if r['model']==model]
        for metric in sorted(set().union(*(r['metrics'] for r in rr))):
            vals=[r['metrics'].get(metric) for r in rr]
            pairs=[(r['metrics'].get(metric),baselines[r['seed']]['metrics'].get(metric)) for r in rr]
            diff=[a-b for a,b in pairs if a is not None and b is not None]
            relative=[100*(a-b)/abs(b) for a,b in pairs if a is not None and b is not None and abs(b)>1e-12]
            row={'model':model,'metric':metric,**estimate(vals)}
            row.update({'difference_'+k:v for k,v in estimate(diff).items()})
            row.update({'relative_percent_'+k:v for k,v in estimate(relative).items()})
            rows.append(row)
    return rows


def run_setting(config, name, out, *, capture=False, arrival_duration=None):
    validate(config)
    records=[]
    for index,seed in enumerate(config['seeds']):
        population_config=deepcopy(config)
        if arrival_duration is not None: population_config['duration']=arrival_duration
        population=generate(population_config,seed)
        baseline=None
        for model in MODELS:
            run=simulate(config,population,seed,model=model)
            if model=='A': baseline=run
            m=kpis(run,config)
            m.update({'paired.'+k:v for k,v in patient_comparison(baseline,run,config).items()})
            records.append({'model':model,'seed':seed,'metrics':m})
            if capture and index==0:
                directory=Path(out)/'sample_runs'/name
                directory.mkdir(parents=True,exist_ok=True)
                (directory/f'{model}.json').write_text(json.dumps(run,allow_nan=False))
        if (index+1)%10==0: print(f'{name}: {index+1}/{len(config["seeds"])} paired replications',flush=True)
    result={'name':name,'configuration':config,'arrival_duration':arrival_duration,'cohort_window_days':WINDOW,'replications':records,'summary':aggregate(records)}
    target=Path(out)/f'{name}.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,allow_nan=False))
    write_csv(Path(out)/f'{name}.csv',result['summary'])
    return result


SWEEPS={
 'signal.tpr':[.4,1.], 'signal.fpr':[0.,.4],
 'signal.review_probability':[.5,1.], 'service.review.mean':[.02,.2],
 'workflow.followup_probability':[.2,.65], 'workflow.avoidable_repeat_rate':[0.,1.],
 'prevalence':[.05,.3], 'workflow.selective_review_probability':[.3,1.],
 'workflow.duplicate_flag_fpr':[0.,.2],
}


def _job(args):
    config,name,out,capture,arrival_duration=args
    return run_setting(config,name,out,capture=capture,arrival_duration=arrival_duration)


def run_study(config, out, sensitivity=False, reference=False, drain=False, workers=1):
    jobs=[]
    for capacity in (2,3):
        for horizon in (180,365):
            c=deepcopy(config); c['capacities']['gp']=capacity; c['duration']=horizon
            jobs.append((c,f'gp{capacity}_{horizon}',out,True,None))
    if reference:
        c=deepcopy(config); c.pop('workflow',None); c['capacities']['gp']=2; c['duration']=180
        jobs.append((c,'original_routing',out,True,None))
    if drain:
        c=deepcopy(config); c['duration']=1500; c['capacities']['gp']=2
        jobs.append((c,'closed_arrivals_drain',out,False,180))
        for parameter,value in [('prevalence',.05),('prevalence',.3),('signal.fpr',0.),('signal.fpr',.4)]:
            c=deepcopy(config);c['duration']=1500;c['capacities']['gp']=2
            target=c;parts=parameter.split('.')
            for part in parts[:-1]: target=target[part]
            target[parts[-1]]=value
            jobs.append((c,f'drain_{parameter.replace(".","_")}_{value}',out,False,180))
    if sensitivity:
        # Both capacities at 180 days: tests interactions with the main bottleneck.
        for capacity in (2,3):
            for parameter,values in SWEEPS.items():
                for value in values:
                    c=deepcopy(config); c['capacities']['gp']=capacity; c['duration']=180
                    target=c
                    parts=parameter.split('.')
                    for part in parts[:-1]: target=target[part]
                    target[parts[-1]]=value
                    name=f'gp{capacity}_{parameter.replace(".","_")}_{value}'
                    jobs.append((c,name,out,False,None))
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results=list(pool.map(_job,jobs))
    else:
        results=[_job(job) for job in jobs]
    summary=[{'experiment':r['name'],**row} for r in results for row in r['summary']]
    write_csv(Path(out)/'comparison.csv',summary)
    (Path(out)/'manifest.json').write_text(json.dumps({'experiments':[r['name'] for r in results],
        'ci_method':'Two-sided paired Student-t 95% Monte Carlo intervals across independent seeds; no multiplicity correction; parameter uncertainty excluded.',
        'cohort':'Same arrivals in [warmup, horizon-60) in all arms; endpoints censored at arrival+60, completion uses service end.',
        'event_metrics':'All work in [warmup,horizon), including pre-warmup arrivals; utilization is not offered workload.',
        'drain':'Closed 180-day arrivals observed to day 1500. Lifecycle claims valid only if unfinished_n is zero in every arm/run.'},indent=2))
    return results
