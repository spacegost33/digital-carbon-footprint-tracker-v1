"""Run in GitHub Actions with the real repository and Flask dependencies."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch
from app import create_app, db
from app.models import User, Activity, Device, EmissionFactor
from app.api import digest
from app.reliability import TelemetryReceipt, ActivityFactor, ChatQuota, ChatGlobalQuota
from app.services import active_factor

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['SECRET_KEY']='ci-only-not-production-secret'
        cls.app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:','SESSION_COOKIE_SECURE':False,'REMEMBER_COOKIE_SECURE':False,'WTF_CSRF_ENABLED':True,'RATELIMIT_ENABLED':False})
        with cls.app.app_context():
            user=User(name='Test',email='ci@example.test',region='IN-KA'); user.set_password('not-a-real-password')
            other=User(name='Other',email='other@example.test',region='IN-KA'); other.set_password('not-a-real-password')
            db.session.add_all([user,other]);db.session.flush();cls.uid=user.id;cls.other=other.id
            device=Device(user_id=user.id,name='CI laptop',platform='windows',token_hash=digest('test-token'))
            db.session.add(device);db.session.commit();cls.did=device.id
        cls.client=cls.app.test_client()
    def setUp(self):
        with self.app.app_context():
            db.session.query(ChatQuota).delete();db.session.query(ChatGlobalQuota).delete();db.session.query(TelemetryReceipt).delete();db.session.query(ActivityFactor).delete();db.session.query(Activity).delete();db.session.get(Device,self.did).active=True;db.session.commit()
        with self.client.session_transaction() as s:s.clear()
    def login(self,uid):
        with self.client.session_transaction() as s:s['_user_id']=str(uid);s['_fresh']=True
    def payload(self):
        return dict(protocol=3,sample_id=str(uuid4()),collected_at=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),duration_seconds=300,cpu_percent=50,memory_mb=3000,energy_kwh=0.0025,measurement_type='estimated',hardware={'battery_percent':80})
    def post(self,p,token='test-token'):
        return self.client.post('/api/telemetry',json=p,headers={'Authorization':'Bearer '+token})
    def test_factor(self):
        with self.app.app_context():self.assertAlmostEqual(active_factor('IN-KA'),0.675)
    def test_duplicate_and_audit(self):
        p=self.payload(); r=self.post(p); self.assertEqual(r.status_code,201,r.get_data(as_text=True));self.assertEqual(self.post(p).status_code,200)
        changed=dict(p,cpu_percent=51); self.assertEqual(self.post(changed).status_code,409)
        with self.app.app_context():
            self.assertEqual(Activity.query.count(),1);self.assertEqual(TelemetryReceipt.query.count(),1);self.assertEqual(ActivityFactor.query.count(),1)
            row=Activity.query.one();self.assertAlmostEqual(row.carbon_kg,0.0025*0.675);self.assertEqual(row.created_at,datetime.fromisoformat(p['collected_at']).replace(tzinfo=None));self.assertEqual(TelemetryReceipt.query.one().hardware['battery_percent'],80)
    def test_bad_json_and_revocation(self):
        self.assertEqual(self.post([]).status_code,400);self.assertEqual(self.post(self.payload(),'bad-token').status_code,401)
        with self.app.app_context():db.session.get(Device,self.did).active=False;db.session.commit()
        self.assertEqual(self.post(self.payload()).status_code,401)
    def test_pages_and_scope(self):
        self.assertEqual(self.post(self.payload()).status_code,201)
        self.login(self.uid)
        for page in ('/agent-setup','/emission-methodology','/carbon-assistant','/dashboard','/devices','/intelligence','/device-intelligence','/energy-optimizer'):
            r=self.client.get(page);self.assertEqual(r.status_code,200,page);self.assertEqual(r.headers.get('Cache-Control'),'private, no-store')
        self.assertIn(b'CI laptop',self.client.get('/agent-setup').data)
        self.login(self.other);self.assertNotIn(b'CI laptop',self.client.get('/agent-setup').data)
    def test_chat_consent_and_provider(self):
        self.login(self.uid)
        import re
        from unittest.mock import Mock
        page=self.client.get('/carbon-assistant').get_data(as_text=True)
        token=re.search(r'<meta name="csrf-token" content="([^"]+)"',page).group(1)
        headers={'X-CSRFToken':token}
        self.assertEqual(self.client.post('/api/carbon-assistant',json={'question':'Test','consent':False},headers=headers).status_code,400)
        with patch.dict(os.environ,{'OPENAI_API_KEY':'fake-test-key','OPENAI_MODEL':'fake-model'}), patch('app.assistant.requests.post') as provider:
            provider.return_value=Mock(ok=True)
            provider.return_value.json.return_value={'output':[{'type':'message','content':[{'type':'output_text','text':'Test answer'}]}]}
            response=self.client.post('/api/carbon-assistant',json={'question':'Test','consent':True,'include_summary':True},headers=headers)
            self.assertEqual(response.status_code,200,response.get_data(as_text=True))
            self.assertEqual(response.json['answer'],'Test answer')
            sent=provider.call_args.kwargs['json']; self.assertFalse(sent['store']); self.assertNotIn('ci@example.test',str(sent)); self.assertNotIn('test-token',str(sent))
    def test_chat_csrf(self):
        self.login(self.uid);self.assertEqual(self.client.post('/api/carbon-assistant',json={'question':'Test','consent':True}).status_code,400)

if __name__=='__main__': unittest.main()
