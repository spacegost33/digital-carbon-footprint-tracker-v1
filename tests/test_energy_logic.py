import importlib.util
from pathlib import Path
from datetime import datetime, timedelta
import unittest

# Pure logic tests can run without importing Flask or the database.
spec = importlib.util.spec_from_file_location('energy_logic', Path(__file__).resolve().parents[1]/'app'/'energy_logic.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

class EnergyTests(unittest.TestCase):
    def test_power(self):
        self.assertAlmostEqual(logic.average_watts(.0025,300),30)
        self.assertIsNone(logic.average_watts(0,300))
        self.assertIsNone(logic.average_watts(.1,0))
    def test_status(self):
        now=datetime(2026,11,28,12)
        self.assertEqual(logic.device_status(True,now-timedelta(minutes=5),now),'Recently reporting')
        self.assertEqual(logic.device_status(True,now-timedelta(minutes=11),now),'Stale / offline')
        self.assertEqual(logic.device_status(False,now,now),'Revoked')
        self.assertEqual(logic.device_status(True,None,now),'Never reported')
    def test_savings(self):
        r=logic.savings(45,8,2,30,8,.7)
        for k,v in {'baseline':10.8,'proposed':8.1,'energy':2.7,'carbon':1.89,'cost':21.6,'percent':25}.items():
            self.assertAlmostEqual(r[k],v)
    def test_validation(self):
        for args in [(45,8,9,30,8,.7),(float('nan'),8,2,30,8,.7),(45,8,2,366,8,.7),(45,8,2,30,-1,.7)]:
            with self.assertRaises(ValueError): logic.savings(*args)
    def test_zero_usage(self):
        self.assertEqual(logic.savings(45,0,0,30,8,.7)['percent'],0)
    def test_chart(self):
        now=datetime(2026,11,28,12)
        r=logic.chart_points([{'time':now,'cpu':None},{'time':now+timedelta(minutes=5),'cpu':50}], 'cpu',100)
        self.assertEqual(len(r['points']),1)
        self.assertEqual(r['points'][0]['x'],332)
        self.assertEqual(logic.chart_points([], 'cpu')['points'],[])
