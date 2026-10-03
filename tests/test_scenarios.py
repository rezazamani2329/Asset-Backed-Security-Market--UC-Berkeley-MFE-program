"""Regression and economic checks for the CSV-calibrated scenario handoff."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from src import scenarios as s
from src.market_data import load_history, read_series
from src.collateral_projection import load_scenarios, project_collateral
ROOT=Path(__file__).resolve().parents[1]

class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((ROOT/'data/scenarios/config.json').read_text())
        cls.data,cls.sources=load_history(ROOT/'data/market','2026-10-03','2026-10-03')
        cls.panel,cls.basis=s.monthly_panel(cls.data,'2000-01-01','2026-10-03')
        cls.mu,cls.phi,cls.resid,cls.params=s.fit_ar(cls.panel)
        cls.paths=pd.read_csv(ROOT/'data/scenarios/scenarios.csv')
        cls.pricing=pd.read_csv(ROOT/'data/scenarios/pricing_rates.csv')
    def test_calendar_and_partial_period(self):
        dates=s.payment_dates('2026-10-03','2031-02-25')
        self.assertEqual(len(dates),54)
        self.assertEqual(dates[1],pd.Timestamp('2026-10-25'))
        self.assertEqual((dates[1]-dates[0]).days,22)
        self.assertEqual(len(s.payment_dates('2026-10-25','2031-02-25')),53)
    def test_bad_calendar(self):
        with self.assertRaises(ValueError):s.payment_dates('2031-03-01','2031-02-25')
    def test_snapshot_guard(self):
        with self.assertRaises(ValueError):load_history(ROOT/'data/market','2026-09-25','2026-10-03')
    def test_cutoff_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.csv';p.write_text('observation_date,SOFR\n2026-09-01,3\n2026-10-01,4\n')
            self.assertEqual(read_series(p,'SOFR','2026-09-15').iloc[-1],3)
            p.write_text('observation_date,SOFR\n2026-09-01,3\n2026-09-01,4\n')
            with self.assertRaises(ValueError):read_series(p,'SOFR')
    def test_missing_numeric_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.csv';p.write_text('observation_date,SOFR\n2026-09-01,.\n2026-09-02,0\n')
            values=read_series(p,'SOFR');self.assertEqual(len(values),1);self.assertEqual(values.iloc[0],0)
    def test_panel_no_partial_month_or_hpi_fill(self):
        self.assertEqual(str(self.panel.index[-1].date()),'2026-07-01')
        self.assertEqual(len(self.panel),319)
        self.assertFalse(self.panel.isna().any().any())
    def test_calibrated_not_demo(self):
        self.assertTrue((self.phi<1).all())
        self.assertGreater(len(self.resid),300)
        self.assertGreater(self.resid.std(),0)
        start=self.paths[self.paths.month==0]
        np.testing.assert_allclose(start.mortgage_rate,self.data['MORTGAGE30US'].iloc[-1])
        np.testing.assert_allclose(start.sofr,self.data['SOFR30DAYAVG'].iloc[-1])
        np.testing.assert_allclose(start.treasury10,self.data['DGS10'].iloc[-1])
    def test_reproducible_simulation(self):
        initial=s.initial_state(self.data,self.panel,self.mu,self.phi,'2026-10-03')
        a,_=s.simulate(self.mu,self.phi,self.resid,initial,4,1000,6,17)
        b,_=s.simulate(self.mu,self.phi,self.resid,initial,4,1000,6,17)
        c,_=s.simulate(self.mu,self.phi,self.resid,initial,4,1000,6,18)
        np.testing.assert_array_equal(a,b);self.assertFalse(np.array_equal(a,c))
    def test_csv_handoff_and_inconsistent_horizon(self):
        loaded=load_scenarios(ROOT/'data/scenarios/scenarios.csv')
        self.assertEqual(set(loaded),set(s.NAMES))
        for name,p in loaded.items():
            self.assertEqual(len(p['rate']),53);self.assertEqual(len(p['hpi']),54)
            self.assertEqual(p['hpi'][0],1.)
            np.testing.assert_allclose(p['rate'],self.paths[(self.paths.scenario==name)&(self.paths.month>0)].mortgage_rate)
        with self.assertRaises(ValueError):load_scenarios(ROOT/'data/scenarios/scenarios.csv',52)
    def test_known_first_coupon_fixing(self):
        p=self.pricing[self.pricing.month==1]
        self.assertTrue((p.reset_date=='2026-09-23').all())
        np.testing.assert_allclose(p.sofr_coupon_decimal,self.data['SOFR30DAYAVG'].loc['2026-09-23']/100,atol=1e-10)
        self.assertTrue((p.fixing_source=='observed').all())
        self.assertTrue((p.coupon_accrual_days==30).all())
        self.assertTrue((p.discount_days==22).all())
    def test_discount_factors(self):
        for _,p in self.pricing.groupby('scenario'):
            self.assertTrue((p.base_discount_factor>0).all())
            self.assertLess(p.base_discount_factor.iloc[0],1)
            self.assertTrue((p.base_discount_factor.diff().dropna()<=1e-12).all())
    def test_historical_stress_exactly_reproduces_hpi(self):
        stress=pd.read_csv(ROOT/'data/scenarios/historical_stress_windows.csv')
        for row in stress.itertuples():
            hist=self.panel.loc[row.historical_start:row.historical_end]
            expected=100*np.exp(np.r_[0,np.cumsum(hist.hpi_log_growth.iloc[1:])])
            actual=self.paths[self.paths.scenario==row.scenario].hpi_index
            np.testing.assert_allclose(actual,expected,rtol=1e-10)
        self.assertLess(self.paths[self.paths.scenario=='severe'].hpi_index.min(),80)
    def test_collateral_balance_identity(self):
        pool=pd.DataFrame({'Loan ID':['a'],'Current Balance':[300000.],'Gross Coupon':[6.75],
            'Credit Score':[760.],'HPI Adjusted LTV':[70.],'Age':[18],
            'Months to Maturity':[342],'dq_bucket':[0]})
        paths=load_scenarios(ROOT/'data/scenarios/scenarios.csv')
        for p in paths.values():
            cf=project_collateral(pool,p['hpi'],p['rate'],53)
            np.testing.assert_allclose(cf.beginning_balance-cf.scheduled_principal-cf.prepayments-cf.defaults,
                cf.ending_balance,atol=1e-6)
    def test_export_uses_actual_csv(self):
        from src import export_results as er
        from unittest.mock import patch
        pool=pd.DataFrame({'Loan ID':['a'],'Current Balance':[300000.],'Gross Coupon':[6.75],
            'Credit Score':[760.],'HPI Adjusted LTV':[70.],'Age':[18],
            'Months to Maturity':[342],'dq_bucket':[0]})
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(er,'TABLES',Path(tmp)):
                er.scenario_tables(pool)
            paths=load_scenarios(ROOT/'data/scenarios/scenarios.csv')
            for name,p in paths.items():
                expected=project_collateral(pool,p['hpi'],p['rate'],53)
                actual=pd.read_csv(Path(tmp)/f'pool_cf_{name}.csv')
                np.testing.assert_allclose(actual.ending_balance,expected.ending_balance)

    def test_loader_rejects_missing_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'s.csv'
            self.paths.iloc[1:].to_csv(p,index=False)
            with self.assertRaises(ValueError):load_scenarios(p)
            pd.concat([self.paths,self.paths.iloc[:1]]).to_csv(p,index=False)
            with self.assertRaises(ValueError):load_scenarios(p)

if __name__=='__main__':unittest.main()
