"""House-price and interest-rate scenario generation.

Design decisions to make (and justify in the report):
  - Deterministic stress scenarios (base / adverse / severe) vs. Monte Carlo paths?
  - HPA model: national vs. state/MSA level? Drift and volatility calibrated to what?
  - Rate paths: needed for prepayment incentive and for SOFR coupon projection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.market_data import load_history, download

ROOT=Path(__file__).resolve().parents[1]
NAMES=('good','base','moderate','severe')
FACTORS=('short_rate','treasury2','treasury10','mortgage_spread','hpi_log_growth')

def payment_dates(valuation_date,call_date):
    start,end=pd.Timestamp(valuation_date),pd.Timestamp(call_date)
    if end<=start or end.day!=25:
        raise ValueError('Call must be a future 25th-of-month date')
    dates=pd.date_range(start.replace(day=1),end,freq='MS')+pd.Timedelta(days=24)
    return pd.DatetimeIndex([start,*dates[(dates>start)&(dates<=end)]])

def monthly_panel(data,start,as_of):
    # Full calendar-month averages; no partial current month in fitting.
    end=pd.Timestamp(as_of).to_period('M')-1
    m={k:s.resample('MS').mean() for k,s in data.items()}
    overlap=pd.concat([m['SOFR'],m['DFF']],axis=1,sort=True).dropna()
    overlap=overlap[overlap.index.to_period('M')<=end]
    if len(overlap)<36:
        raise ValueError('Need at least 36 months of SOFR/DFF overlap')
    basis=float((overlap.SOFR-overlap.DFF).median())
    short=m['SOFR'].combine_first(m['DFF']+basis)
    frame=pd.DataFrame({'short_rate':short,'treasury2':m['DGS2'],'treasury10':m['DGS10'],
        'mortgage_spread':m['MORTGAGE30US']-m['DGS10'],
        'hpi_log_growth':np.log(m['HPIPONM226S']).diff()})
    frame=frame[(frame.index>=pd.Timestamp(start))&(frame.index.to_period('M')<=end)]
    frame=frame.dropna()
    if len(frame)<120 or not frame.index.to_period('M').equals(pd.period_range(frame.index[0],frame.index[-1],freq='M')):
        raise ValueError('Need at least 120 consecutive complete joint monthly observations')
    return frame,basis

def fit_ar(panel):
    """Centered AR(1) per factor, with jointly retained residuals.
    Persistence constrained to [0,.995] to give finite long-horizon forecasts.
    """
    a=panel.to_numpy(float);mu=a.mean(axis=0);x=a[:-1]-mu;y=a[1:]-mu
    denominator=(x*x).sum(axis=0)
    if (denominator<=1e-14).any():raise ValueError('Constant calibration factor')
    unconstrained=(x*y).sum(axis=0)/denominator
    phi=np.clip(unconstrained,0,.995)
    fitted=mu+phi*(a[:-1]-mu)
    residual=a[1:]-fitted;residual-=residual.mean(axis=0)
    diagnostics=pd.DataFrame({'factor':FACTORS,'mean':mu,'phi_raw':unconstrained,'phi':phi,
        'residual_sd':residual.std(axis=0,ddof=1),'in_sample_rmse':np.sqrt(((a[1:]-fitted)**2).mean(axis=0)),
        'half_life_months':np.where(phi>0,np.log(.5)/np.log(np.maximum(phi,1e-10)),0)})
    return mu,phi,residual,diagnostics

def rolling_validation(panel,min_train=120,horizons=(1,12)):
    # Uses today's revised history: diagnostic pseudo-out-of-sample, not vintage backtest.
    records=[]
    for h in horizons:
        errors=[];naive=[]
        for end in range(min_train,len(panel)-h+1,3):
            mu,phi,_,_=fit_ar(panel.iloc[:end]);last=panel.iloc[end-1].to_numpy()
            forecast=mu+phi**h*(last-mu);actual=panel.iloc[end+h-1].to_numpy()
            errors.append(forecast-actual);naive.append(last-actual)
        if not errors:continue
        e=np.asarray(errors);b=np.asarray(naive)
        for j,name in enumerate(FACTORS):
            records.append({'factor':name,'horizon_months':h,'origins':len(e),
                'model_rmse':float(np.sqrt((e[:,j]**2).mean())),
                'no_change_rmse':float(np.sqrt((b[:,j]**2).mean()))})
    return pd.DataFrame(records)

def initial_state(data,panel,mu,phi,as_of):
    m=float(data['MORTGAGE30US'].iloc[-1]);t=float(data['DGS10'].iloc[-1])
    hpi_months=pd.Timestamp(as_of).to_period('M').ordinal-panel.index[-1].to_period('M').ordinal
    hpa=mu[-1]+phi[-1]**hpi_months*(panel.iloc[-1,-1]-mu[-1])
    return np.array([data['SOFR'].iloc[-1],data['DGS2'].iloc[-1],t,m-t,hpa],float)

def simulate(mu,phi,residual,initial,n_months,n_paths,block_months,seed):
    if n_paths<1000 or block_months<1 or block_months>len(residual):
        raise ValueError('Need >=1000 simulations and a valid residual block length')
    rng=np.random.default_rng(seed)
    states=np.empty((n_paths,n_months+1,len(FACTORS)));states[:,0]=initial
    # Sample entire vector blocks together: same historical month for all factors.
    floors=np.array([0.,0.,0.,.01,-np.inf])
    count=np.zeros(len(FACTORS),int)
    for t in range(1,n_months+1):
        offset=(t-1)%block_months
        if offset==0:starts=rng.integers(0,len(residual)-block_months+1,size=n_paths)
        next_state=mu+phi*(states[:,t-1]-mu)+residual[starts+offset]
        count+=(next_state<floors).sum(axis=0)
        states[:,t]=np.maximum(next_state,floors)
    return states,count

def select_scenarios(states,dates,bands):
    # Condition on cumulative HPI growth. Average all factors on the SAME selected paths.
    # Four cases are conditional mean sensitivities, not a four-point pricing quadrature.
    hpi=np.exp(np.cumsum(states[:,1:,-1],axis=1))
    hpi=np.column_stack([np.ones(len(states)),hpi])
    order=np.argsort(hpi[:,-1],kind='stable');rank=np.empty(len(order));rank[order]=(np.arange(len(order))+.5)/len(order)
    frames=[];selection=[]
    for name in NAMES:
        lo,hi=bands[name]
        if not 0<=lo<hi<=1:raise ValueError('Invalid scenario percentile band')
        mask=(rank>=lo)&(rank<hi)
        if mask.sum()<20:raise ValueError('Too few selected paths')
        state=states[mask].mean(axis=0)
        frame=pd.DataFrame({'scenario':name,'month':np.arange(len(dates)),'date':dates.strftime('%Y-%m-%d'),
            'mortgage_rate':state[:,2]+state[:,3],'hpi_index':100*hpi[mask].mean(axis=0),
            'sofr_overnight':state[:,0],'treasury2':state[:,1],'treasury10':state[:,2],
            'mortgage_spread':state[:,3]})
        frames.append(frame)
        selection.append({'scenario':name,'lower_hpi_percentile':lo*100,'upper_hpi_percentile':hi*100,
            'selected_paths':int(mask.sum()),'terminal_hpi_change_pct':float(frame.hpi_index.iloc[-1]-100),
            'minimum_hpi_change_pct':float(frame.hpi_index.min()-100),
            'terminal_mortgage_rate':float(frame.mortgage_rate.iloc[-1]),'terminal_sofr_overnight':float(frame.sofr_overnight.iloc[-1])})
    return pd.concat(frames,ignore_index=True),pd.DataFrame(selection)

def historical_stresses(panel, initial, dates, scenarios, summary):
    """Replay joint historical changes, reanchored to current observed rates.
    Moderate selects the 10th percentile historical horizon HPI return;
    severe selects the worst observed horizon. Windows overlap, so these
    percentiles describe the sample and are not event probabilities.
    """
    n=len(dates)-1
    candidates=[]
    for start in range(len(panel)-n):
        block=panel.iloc[start:start+n+1]
        terminal=float(np.exp(block.hpi_log_growth.iloc[1:].sum()))
        candidates.append((terminal,start))
    if len(candidates)<60:raise ValueError('Insufficient historical stress windows')
    ordered=sorted(candidates)
    records=[];frames=[]
    for name,q in [('moderate',.10),('severe',0.)]:
        _,start=ordered[int(round(q*(len(ordered)-1)))]
        history=panel.iloc[start:start+n+1]
        state=initial+history.to_numpy()-history.iloc[0].to_numpy()
        floors=np.array([0.,0.,0.,.01,-np.inf])
        hits=int((state[:,:4]<floors[:4]).sum())
        state=np.maximum(state,floors)
        hpi=100*np.exp(np.r_[0.,np.cumsum(history.hpi_log_growth.iloc[1:].to_numpy())])
        frame=pd.DataFrame({'scenario':name,'month':np.arange(len(dates)),'date':dates.strftime('%Y-%m-%d'),
            'mortgage_rate':state[:,2]+state[:,3],'hpi_index':hpi,'sofr_overnight':state[:,0],
            'treasury2':state[:,1],'treasury10':state[:,2],'mortgage_spread':state[:,3]})
        frames.append(frame)
        records.append({'scenario':name,'historical_start':str(history.index[0].date()),
            'historical_end':str(history.index[-1].date()),'historical_hpi_percentile':q*100,
            'candidate_windows':len(candidates),'rate_floor_hits':hits,
            'terminal_hpi_change_pct':hpi[-1]-100,'minimum_hpi_change_pct':hpi.min()-100,
            'terminal_mortgage_rate':frame.mortgage_rate.iloc[-1],
            'terminal_sofr_overnight':frame.sofr_overnight.iloc[-1]})
    scenarios=pd.concat([scenarios[scenarios.scenario.isin(['good','base'])],*frames],ignore_index=True)
    stress=pd.DataFrame(records)
    summary=summary[summary.scenario.isin(['good','base'])].copy()
    summary['method']='conditional mean from calibrated simulation'
    stress['method']='joint historical stress replay, reanchored to current rates'
    return scenarios,pd.concat([summary,stress],ignore_index=True),stress

def rate_handoff(paths,data,as_of):
    """Monthly coupon-index proxy and scenario discounting, kept separate.
    First future coupon reset is known for this October valuation; use published fixing.
    Future index approximates a lagged 30-day compounded average of daily rate paths.
    Calendar approximation is explicit; not a market OIS curve.
    """
    from pandas.tseries.holiday import USFederalHolidayCalendar, GoodFriday
    from pandas.tseries.offsets import CustomBusinessDay
    class SecuritiesCalendar(USFederalHolidayCalendar):
        rules=USFederalHolidayCalendar.rules+[GoodFriday]
    bd=CustomBusinessDay(calendar=SecuritiesCalendar())
    full=[];pricing=[]
    for name,g in paths.groupby('scenario',sort=False):
        g=g.sort_values('month').copy();dates=pd.DatetimeIndex(pd.to_datetime(g.date));v=dates[0]
        daily_index=pd.date_range(v-pd.Timedelta(days=100),dates[-1],freq='D')
        hist=data['SOFR'].reindex(daily_index,method='ffill')
        future=daily_index>v
        hist.loc[future]=np.interp(daily_index[future].asi8,dates.asi8,g.sofr_overnight)
        if hist.isna().any():raise ValueError('Insufficient historical SOFR for resets')
        # Weekends carry the preceding rate with simple n/360 accrual for each business interval.
        def compounded_average(reset):
            start=reset-pd.Timedelta(days=30)
            if reset<=pd.Timestamp(as_of):
                available=data['SOFR30DAYAVG'].loc[:reset]
                if available.empty or (reset-available.index[-1]).days>5:raise ValueError('Missing known coupon fixing')
                return float(available.iloc[-1]),'observed'
            days=pd.date_range(start,reset-pd.Timedelta(days=1),freq='D')
            product=1.;i=0
            while i<len(days):
                d=days[i];anchor=bd.rollback(d);end=anchor+bd
                n=min((end-d).days,len(days)-i)
                rate=float(hist.loc[anchor])
                product*=1+rate/100*n/360;i+=n
            return (product-1)*360/30*100,'projected'
        sofr=[float(data['SOFR30DAYAVG'].iloc[-1])];rows=[]
        dcf=1.
        for j in range(1,len(g)):
            pay=dates[j];accrual_start=(pay-pd.DateOffset(months=1)).replace(day=25)
            reset=accrual_start-2*bd
            coupon,source=compounded_average(reset);sofr.append(coupon)
            period=pd.date_range(dates[j-1],pay-pd.Timedelta(days=1),freq='D')
            # Piecewise daily scenario overnight path; discounts are conditional scenario PV inputs.
            log_factor=np.log1p(hist.reindex(period).to_numpy()/100/360).sum()
            dcf*=float(np.exp(-log_factor))
            rows.append({'scenario':name,'month':j,'date':str(pay.date()),'reset_date':str(reset.date()),
                'accrual_start':str(accrual_start.date()),'coupon_accrual_days':(pay-accrual_start).days,
                'discount_days':(pay-dates[j-1]).days,'sofr_coupon_decimal':coupon/100,
                'fixing_source':source,'base_discount_factor':dcf,
                'discount_basis':'physical_scenario_overnight_no_credit_spread'})
        g['sofr']=sofr;full.append(g);pricing.extend(rows)
    return pd.concat(full,ignore_index=True),pd.DataFrame(pricing)

def write_chart(paths,path):
    # Standard-library SVG, works without optional plotting dependencies.
    colors=dict(zip(NAMES,['#17845b','#2463c4','#c58015','#c43f4c']))
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="880"><rect width="1000" height="880" fill="white"/>',
           '<text x="70" y="26" font-family="sans-serif" font-size="18">STACR: CSV-calibrated historical scenarios</text>']
    for panel,(key,label) in enumerate([('mortgage_rate','Mortgage rate (%)'),('sofr','30-day SOFR coupon index (%)'),('hpi_index','House prices (initial = 100)')]):
        top=85+panel*250;lo,hi=paths[key].min(),paths[key].max();pad=max((hi-lo)*.1,.1);lo-=pad;hi+=pad
        parts.append(f'<text x="70" y="{top-15}" font-family="sans-serif" font-size="17">{label}</text>')
        for value in np.linspace(lo,hi,5):
            y=top+175*(hi-value)/(hi-lo)
            parts.append(f'<path d="M70 {y} H950" stroke="#ddd"/><text x="12" y="{y+4}" font-size="12">{value:.2f}</text>')
        for name,g in paths.groupby('scenario',sort=False):
            points=' '.join(f'{70+880*m/paths.month.max():.2f},{top+175*(hi-v)/(hi-lo):.2f}' for m,v in zip(g.month,g[key]))
            parts.append(f'<polyline points="{points}" fill="none" stroke="{colors[name]}" stroke-width="2.5"/>')
        parts.append(f'<text x="70" y="{top+198}" font-size="12">{paths.date.iloc[0]}</text><text x="865" y="{top+198}" font-size="12">{paths.date.iloc[-1]}</text>')
    for i,name in enumerate(NAMES):parts.append(f'<text x="{220+i*160}" y="845" fill="{colors[name]}" font-size="16">{name}</text>')
    path.write_text(''.join(parts)+'</svg>',encoding='utf-8')

def run(config,root=ROOT):
    market=root/config['market_dir'];out=root/config['output_dir']
    data,provenance=load_history(market,config['valuation_date'],config['snapshot_as_of'])
    panel,basis=monthly_panel(data,config['calibration_start'],config['valuation_date'])
    mu,phi,residual,parameters=fit_ar(panel)
    initial=initial_state(data,panel,mu,phi,config['valuation_date'])
    dates=payment_dates(config['valuation_date'],config['call_date'])
    states,floors=simulate(mu,phi,residual,initial,len(dates)-1,config['n_paths'],config['block_months'],config['seed'])
    paths,summary=select_scenarios(states,dates,config['scenario_percentile_bands'])
    simulated_summary=summary.copy()
    paths,summary,stress=historical_stresses(panel,initial,dates,paths,summary)
    paths,pricing=rate_handoff(paths,data,config['valuation_date'])
    validation=rolling_validation(panel)
    out.mkdir(parents=True,exist_ok=True)
    tables={'scenarios':paths,'pricing_rates':pricing,'scenario_summary':summary,'calibration_parameters':parameters,
        'market_sources':provenance,'validation':validation,'calibration_monthly':panel.rename_axis('date').reset_index(),
        'simulated_quantile_diagnostics':simulated_summary,'historical_stress_windows':stress,
        'residual_correlations':pd.DataFrame(np.corrcoef(residual,rowvar=False),index=FACTORS,columns=FACTORS).rename_axis('factor').reset_index()}
    for name,table in tables.items():table.to_csv(out/f'{name}.csv',index=False,float_format='%.10f')
    metadata={'config':config,'method':'AR1 plus joint residual block bootstrap for base/good; historical replay for moderate/severe; physical measure',
        'calibration_start':str(panel.index[0].date()),'calibration_end':str(panel.index[-1].date()),
        'calibration_months':len(panel),'projection_periods':len(dates)-1,'sofr_dff_basis_pp':basis,
        'floor_hits':dict(zip(FACTORS,map(int,floors))),'simulated_observations_per_factor':config['n_paths']*(len(dates)-1),
        'limits':['Not an OIS/futures-implied curve or risk-neutral pricing model',
          'HPI release lag: latest observed growth nowcast to valuation; current LTV anchors HPI=100',
          'Pre-2018 short rates use DFF plus median overlapping SOFR-DFF basis',
          'Conditional scenario averages do not equal expected tranche prices',
          'Moderate/severe historical-window ranks are not scenario probabilities; joint historic rate changes are reanchored to current rates',
          'Backtest uses current-vintage history and is not a real-time vintage backtest',
          'Known SOFR resets use published averages; future reset calendar uses US federal holidays plus Good Friday',
          'Scheduled dates are unadjusted 25ths; payment business-day adjustments belong to waterfall'],
        'sources':provenance.to_dict('records')}
    (out/'scenario_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    write_chart(paths,out/'scenario_paths.svg')
    return paths,summary,validation

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'data/scenarios/config.json')
    parser.add_argument('--download',action='store_true',help='Refresh standard FRED CSVs before calibration')
    args=parser.parse_args();config=json.loads(args.config.read_text(encoding='utf-8-sig'))
    if args.download:download(ROOT/config['market_dir'])
    paths,summary,validation=run(config)
    print(summary.to_string(index=False));print(f'Wrote {len(paths)} rows to {ROOT/config["output_dir"]}')
    print(validation.to_string(index=False))
if __name__=='__main__':main()
