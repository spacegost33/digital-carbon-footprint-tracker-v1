"""CarbonTrack agent v3. Run only on an authorized computer with informed consent."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

import psutil
import requests
from dotenv import dotenv_values

HOME = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'CarbonTrack' if os.name == 'nt' else Path.home() / '.carbontrack'
CONFIG = HOME / 'config.json'


def validate_config(cfg):
    url = str(cfg['CARBONTRACK_API_URL']).rstrip('/')
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
        raise ValueError('Use the HTTPS website origin, without a path.')
    token = str(cfg['CARBONTRACK_DEVICE_TOKEN']).strip()
    if not 1 <= len(token) <= 256 or token == 'PASTE_ONE_TIME_DEVICE_TOKEN_HERE':
        raise ValueError('Enter the token from Devices & agents.')
    interval = int(cfg.get('CARBONTRACK_INTERVAL_SECONDS',300))
    idle = float(cfg.get('CARBONTRACK_IDLE_WATTS',10)); load = float(cfg.get('CARBONTRACK_LOAD_WATTS',45))
    if not 30 <= interval <= 3600 or not (math.isfinite(idle) and math.isfinite(load) and 0 < idle <= load <= 5000):
        raise ValueError('Choose interval 30–3600 seconds and valid idle/load watts.')
    return dict(url=url, token=token, interval=interval, idle=idle, load=load)


def configure():
    print('CarbonTrack collects CPU and RAM usage, runtime, estimated energy, and available battery/CPU/GPU sensor readings. No files, browsing history, keystrokes or screen contents are collected.')
    if input('I own this device or have permission to monitor it. Continue? [y/N] ').strip().lower() != 'y':
        raise SystemExit('Setup cancelled.')
    data = dict(CARBONTRACK_API_URL=input('CarbonTrack HTTPS website URL: ').strip(), CARBONTRACK_DEVICE_TOKEN=getpass('Device token from the website (hidden): ').strip(),
                CARBONTRACK_INTERVAL_SECONDS=input('Reporting interval seconds [300]: ').strip() or '300', CARBONTRACK_IDLE_WATTS=input('Estimated idle watts [10]: ').strip() or '10', CARBONTRACK_LOAD_WATTS=input('Estimated full-load watts [45]: ').strip() or '45')
    cfg = validate_config(data)
    HOME.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp = CONFIG.with_suffix('.tmp')
    fd = os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(data,f)
    os.replace(tmp,CONFIG)
    print('Configuration saved to your local user profile. Wattages are estimates; enter calibrated values where available.')
    return cfg


def get_config(force=False):
    if force: return configure()
    if CONFIG.exists():
        return validate_config(json.loads(CONFIG.read_text(encoding='utf-8')))
    # Backward-compatible with existing Python agent installations. Do not import config from an arbitrary cwd for an executable.
    if not getattr(sys,'frozen',False):
        values = {**dotenv_values(Path(__file__).resolve().parent/'.env'), **os.environ}
        if values.get('CARBONTRACK_API_URL') and values.get('CARBONTRACK_DEVICE_TOKEN'):
            return validate_config(values)
    return configure()


class Queue:
    def __init__(self,path):
        self.db=sqlite3.connect(path, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS pending (id TEXT PRIMARY KEY, payload TEXT NOT NULL, rejected TEXT)')
        self.db.commit()
    def add(self,payload):
        if self.count() >= 10000:
            raise RuntimeError('Local queue full. Synchronize or inspect rejected records before continuing; no records were deleted.')
        with self.db:
            self.db.execute('INSERT INTO pending(id,payload) VALUES (?,?)',(payload['sample_id'],json.dumps(payload,allow_nan=False)))
    def next(self,limit=20):
        return self.db.execute('SELECT id,payload FROM pending WHERE rejected IS NULL ORDER BY rowid LIMIT ?', (limit,)).fetchall()
    def ack(self,sid):
        with self.db: self.db.execute('DELETE FROM pending WHERE id=?',(sid,))
    def reject(self,sid,reason):
        with self.db: self.db.execute('UPDATE pending SET rejected=? WHERE id=?',(reason,sid))
    def count(self): return self.db.execute('SELECT COUNT(*) FROM pending').fetchone()[0]
    def rejected_count(self): return self.db.execute('SELECT COUNT(*) FROM pending WHERE rejected IS NOT NULL').fetchone()[0]
    def close(self): self.db.close()


@contextmanager
def single_instance(path):
    with open(path,'a+b') as f:
        f.seek(0,2)
        if f.tell()==0: f.write(b'0'); f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise SystemExit('This device profile is already being monitored by another agent.')
        try: yield
        finally:
            f.seek(0)
            if os.name=='nt': msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def rapl_snapshot():
    """Only top-level Intel CPU packages; not nested domains (avoid double counting)."""
    found={}
    for root in Path('/sys/class/powercap').glob('intel-rapl:[0-9]*'):
        if root.name.count(':')!=1: continue
        try:
            if not (root/'name').read_text().strip().startswith('package-'): continue
            energy=int((root/'energy_uj').read_text()); maximum=int((root/'max_energy_range_uj').read_text())
            if 0<=energy<=maximum and maximum>0: found[str(root)]=(energy,maximum)
        except (OSError,ValueError): pass
    return found


def rapl_wh(before,after,elapsed):
    if not before or set(before)!=set(after): return None
    total=0
    for key,(start,maximum) in before.items():
        end,maximum2=after[key]
        if maximum!=maximum2 or maximum<=0 or maximum <= elapsed*1000*1e6: return None  # ambiguous multiple wraps
        delta=(end-start)%maximum
        if delta > elapsed*1000*1e6: return None
        total+=delta
    wh=total/3.6e9
    return wh if wh<=elapsed*1000/3600 else None


def hardware():
    result={'logical_cores':psutil.cpu_count() or 1,'total_ram_mb':round(psutil.virtual_memory().total/1048576,2)}
    try:
        battery=psutil.sensors_battery()
        if battery is not None:
            percent=float(battery.percent)
            if math.isfinite(percent) and 0<=percent<=100: result['battery_percent']=round(percent,2)
            if isinstance(battery.power_plugged,bool): result['plugged_in']=battery.power_plugged
    except (AttributeError,NotImplementedError,OSError,ValueError,TypeError): pass
    executable=shutil.which('nvidia-smi')
    if executable:
        try:
            output=subprocess.run([executable,'--query-gpu=power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,check=True)
            powers=[float(x.strip()) for x in output.stdout.splitlines() if x.strip()]
            if powers and all(math.isfinite(x) and 0<=x<=2000 for x in powers) and sum(powers)<=2000: result['gpu_power_w']=round(sum(powers),2)
        except (OSError,ValueError,subprocess.SubprocessError): pass
    return result


def collect(cfg):
    duration=energy_wh=cpu_weighted=mem_weighted=package_wh=0.0
    package_complete=True
    while duration<cfg['interval']:
        sample=min(5,cfg['interval']-duration)
        start=time.monotonic(); wall=time.time(); before=rapl_snapshot()
        cpu=psutil.cpu_percent(interval=sample)
        elapsed=time.monotonic()-start
        if elapsed<=0 or max(elapsed,time.time()-wall)>sample+3:
            print('Interrupted sample skipped.'); continue
        mem=psutil.virtual_memory().used/1048576
        watts=cfg['idle']+(cfg['load']-cfg['idle'])*cpu/100
        energy_wh+=watts*elapsed/3600; duration+=elapsed; cpu_weighted+=cpu*elapsed; mem_weighted+=mem*elapsed
        reading=rapl_wh(before,rapl_snapshot(),elapsed)
        if reading is None: package_complete=False
        else: package_wh+=reading
    collected=datetime.now(timezone.utc).isoformat()
    hw=hardware()
    if package_complete: hw['cpu_package_wh']=round(package_wh,9)
    return dict(protocol=3,sample_id=str(uuid4()),collected_at=collected,duration_seconds=round(duration,3),cpu_percent=round(cpu_weighted/duration,2),memory_mb=round(mem_weighted/duration,2),energy_kwh=round(energy_wh/1000,9),measurement_type='estimated',hardware=hw)


def sync(queue,cfg,session):
    for sid,payload in queue.next():
        try:
            response=session.post(cfg['url']+'/api/telemetry',json=json.loads(payload),headers={'Authorization':'Bearer '+cfg['token']},timeout=(5,10),allow_redirects=False)
        except requests.RequestException:
            print('Network unavailable; records retained.'); break
        if response.status_code in (401,403):
            raise SystemExit('Device token invalid or revoked. Queued records retained; monitoring stopped.')
        if response.status_code in (400,409,413,422):
            queue.reject(sid,'HTTP '+str(response.status_code)); print('Rejected record retained for inspection:',sid); continue
        if response.status_code in (200,201):
            try: data=response.json()
            except ValueError: break
            if isinstance(data,dict) and data.get('sample_id')==sid and data.get('status') in ('accepted','duplicate'):
                queue.ack(sid); print('Synced:',sid,data['status']); continue
        print('Upload not acknowledged; retained. HTTP',response.status_code); break


def startup(enable):
    if os.name!='nt': raise SystemExit('Automatic startup option is for Windows only.')
    folder=Path(os.environ['APPDATA'])/'Microsoft'/'Windows'/'Start Menu'/'Programs'/'Startup'
    shortcut=folder/'CarbonTrack Agent.lnk'
    if not enable:
        shortcut.unlink(missing_ok=True); print('Automatic startup disabled.'); return
    if not getattr(sys,'frozen',False): raise SystemExit('Use the packaged Windows executable for automatic startup.')
    if not CONFIG.exists(): raise SystemExit('Configure the agent first.')
    if input('Start the visible CarbonTrack monitoring console whenever you sign in? [y/N] ').strip().lower()!='y': return
    folder.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'CT_SHORTCUT':str(shortcut),'CT_EXECUTABLE':str(Path(sys.executable).resolve())}
    script="$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:CT_SHORTCUT); $s.TargetPath=$env:CT_EXECUTABLE; $s.WorkingDirectory=[IO.Path]::GetDirectoryName($env:CT_EXECUTABLE); $s.Save()"
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=env,check=True)
    print('Startup enabled. Keep the executable in this location. Use --disable-startup to remove it.')


def main():
    parser=argparse.ArgumentParser(description='CarbonTrack consent-based monitoring agent')
    mode=parser.add_mutually_exclusive_group()
    for flag in ('once','sync-only','configure','enable-startup','disable-startup','self-test','queue-status'):
        mode.add_argument('--'+flag,action='store_true')
    args=parser.parse_args()
    if args.self_test:
        print('CarbonTrack Agent v3: imports OK'); return
    if args.enable_startup or args.disable_startup:
        startup(args.enable_startup); return
    try: cfg=get_config(args.configure)
    except (ValueError,KeyError,OSError,TypeError) as exc:
        raise SystemExit('Invalid configuration. Run --configure and enter valid values.') from None
    if args.configure: return
    HOME.mkdir(parents=True,exist_ok=True,mode=0o700)
    identity=hashlib.sha256((cfg['url']+'\0'+cfg['token']).encode()).hexdigest()[:32]
    with single_instance(HOME/(identity+'.lock')):
        queue=Queue(HOME/(identity+'.sqlite3'))
        try:
            if args.queue_status:
                print('Local database:',HOME/(identity+'.sqlite3')); print('Total queued:',queue.count(),'Rejected:',queue.rejected_count()); return
            with requests.Session() as session:
                print('CarbonTrack running. Whole-device energy estimated. Press Ctrl+C to stop.')
                sync(queue,cfg,session)
                if args.sync_only: return
                while True:
                    if queue.count()>=10000: raise RuntimeError('Queue full; data retained. Stop and resolve pending records.')
                    payload=collect(cfg); queue.add(payload); sync(queue,cfg,session)
                    print('Local records:',queue.count(),'Rejected (retained):',queue.rejected_count())
                    if args.once: break
        finally: queue.close()

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('\nCarbonTrack stopped. Completed queued records retained.')
    except (RuntimeError,sqlite3.Error,OSError) as exc: print('Agent stopped:',type(exc).__name__,str(exc)); sys.exit(1)
