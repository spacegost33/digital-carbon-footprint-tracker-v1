"""Offline tests for data validation, queue durability and sensor math."""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from uuid import uuid4
import requests

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=spec_from_file_location(name,ROOT/path); mod=module_from_spec(spec); spec.loader.exec_module(mod); return mod
v=load('ct_validation','app/telemetry_validation.py')
a=load('ct_agent','monitoring_agent/agent.py')

def sample(now=None):
    now=now or datetime.now(timezone.utc)
    return dict(protocol=3,sample_id=str(uuid4()),collected_at=now.isoformat(),duration_seconds=300,cpu_percent=30,memory_mb=2048,energy_kwh=0.0025,measurement_type='estimated',hardware={'battery_percent':75,'plugged_in':False})

class Validation(unittest.TestCase):
    def test_valid_and_replay_fingerprint(self):
        now=datetime.now(timezone.utc); data=sample(now)
        first=v.validate(data,now); second=v.validate(dict(reversed(list(data.items()))),now)
        self.assertEqual(first[4],second[4]); self.assertEqual(first[1],data['sample_id'])
        data['cpu_percent']=31; self.assertNotEqual(v.validate(data,now)[4],first[4])
    def test_bad_json_types(self):
        for data in (None,[],{},dict(sample(),cpu_percent=True),dict(sample(),energy_kwh=float('nan')),dict(sample(),cpu_percent=101),dict(sample(),energy_kwh=99),dict(sample(),measurement_type='measured'),dict(sample(),hardware={'battery_percent':101})):
            with self.subTest(data=data), self.assertRaises((ValueError,TypeError,KeyError)): v.validate(data)
    def test_timestamp_preserved(self):
        now=datetime.now(timezone.utc); observed=now-timedelta(days=2)
        self.assertEqual(v.validate(sample(observed),now)[2],observed.replace(tzinfo=None))
        for d in (-31,1):
            with self.assertRaises(ValueError): v.validate(sample(now+timedelta(days=d)),now)
    def test_legacy(self):
        x=sample(); [x.pop(k) for k in ('protocol','sample_id','collected_at','hardware')]
        self.assertIsNone(v.validate(x)[1])
    def test_hardware_is_separate(self):
        x=sample(); x['hardware']['cpu_package_wh']=0.3
        values,_,_,hw,_=v.validate(x)
        self.assertEqual(values['energy_kwh'],0.0025); self.assertEqual(hw['cpu_package_wh'],0.3)

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'q.sqlite3'; self.q=a.Queue(self.path)
        self.cfg={'url':'https://example.com','token':'fake-test-token'}
    def tearDown(self): self.q.close(); self.tmp.cleanup()
    def test_persistent(self):
        x=sample(); self.q.add(x); self.q.close(); self.q=a.Queue(self.path); self.assertEqual(self.q.next()[0][0],x['sample_id'])
    def test_failed_network_retains(self):
        self.q.add(sample()); session=Mock(); session.post.side_effect=requests.ConnectionError('offline'); a.sync(self.q,self.cfg,session); self.assertEqual(self.q.count(),1)
    def test_duplicate_ack(self):
        x=sample(); self.q.add(x); session=Mock(); session.post.return_value.status_code=200; session.post.return_value.json.return_value={'sample_id':x['sample_id'],'status':'duplicate'}; a.sync(self.q,self.cfg,session); self.assertEqual(self.q.count(),0)
    def test_wrong_ack_retained(self):
        self.q.add(sample()); session=Mock(); session.post.return_value.status_code=201; session.post.return_value.json.return_value={'sample_id':'different','status':'accepted'}; a.sync(self.q,self.cfg,session); self.assertEqual(self.q.count(),1)
    def test_rejected_retained(self):
        self.q.add(sample()); session=Mock(); session.post.return_value.status_code=409; a.sync(self.q,self.cfg,session); self.assertEqual(self.q.rejected_count(),1); self.assertEqual(self.q.next(),[])
    def test_revocation_stops(self):
        self.q.add(sample()); session=Mock(); session.post.return_value.status_code=401
        with self.assertRaises(SystemExit): a.sync(self.q,self.cfg,session)
        self.assertEqual(self.q.count(),1)

class AgentTests(unittest.TestCase):
    def test_rapl_wh_and_wrap(self):
        # 3.6 MJ microjoules per Wh conversion; 10 J over a second.
        self.assertAlmostEqual(a.rapl_wh({'a':(0,10_000_000_000)},{'a':(10_000_000,10_000_000_000)},1),10/3600)
        self.assertAlmostEqual(a.rapl_wh({'a':(9_995_000_000,10_000_000_000)},{'a':(5_000_000,10_000_000_000)},1),10/3600)
        self.assertIsNone(a.rapl_wh({}, {}, 1))
    def test_config_requires_https(self):
        with self.assertRaises(ValueError): a.validate_config({'CARBONTRACK_API_URL':'http://example.com','CARBONTRACK_DEVICE_TOKEN':'x'})
        self.assertEqual(a.validate_config({'CARBONTRACK_API_URL':'https://example.com','CARBONTRACK_DEVICE_TOKEN':'x'})['interval'],300)

if __name__=='__main__': unittest.main()
