"""Pure validation for versioned endpoint observations."""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import UUID


def bounded(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Expected a JSON number.')
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Number out of range.')
    return value


def validate(data, now=None):
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object.')
    now = now or datetime.now(timezone.utc)
    if not all(k in data for k in ('duration_seconds', 'cpu_percent', 'memory_mb', 'energy_kwh')):
        raise ValueError('Missing telemetry fields.')
    duration = bounded(data['duration_seconds'], 0.001, 86400)
    energy = bounded(data['energy_kwh'], 0, min(100, duration * 5000 / 3600000 + 1e-6))
    result = dict(duration_seconds=duration, cpu_percent=bounded(data['cpu_percent'], 0, 100), memory_mb=bounded(data['memory_mb'], 0, 1048576), energy_kwh=energy)
    if data.get('measurement_type', 'estimated') != 'estimated':
        raise ValueError('Whole-device telemetry must be estimated.')
    if 'sample_id' not in data and 'collected_at' not in data and 'protocol' not in data:
        return result, None, now.replace(tzinfo=None), {}, None
    if data.get('protocol') != 3 or isinstance(data.get('protocol'), bool):
        raise ValueError('Unsupported protocol.')
    sid = str(UUID(str(data['sample_id'])))
    if not isinstance(data['collected_at'], str) or len(data['collected_at']) > 40:
        raise ValueError('Invalid timestamp.')
    collected = datetime.fromisoformat(data['collected_at'].replace('Z','+00:00'))
    if collected.tzinfo is None:
        raise ValueError('Timestamp must contain a timezone.')
    collected = collected.astimezone(timezone.utc)
    # Permit minor clock skew; old records are retained rather than counted at upload time.
    if collected > now + timedelta(minutes=2) or collected < now - timedelta(days=30):
        raise ValueError('Timestamp outside allowed 30-day collection window.')
    hw = data.get('hardware', {})
    if not isinstance(hw, dict) or set(hw) - {'battery_percent','plugged_in','cpu_package_wh','gpu_power_w','logical_cores','total_ram_mb'}:
        raise ValueError('Invalid hardware observations.')
    cleaned = {}
    for key, maximum in [('battery_percent',100), ('cpu_package_wh', duration*1000/3600+0.001), ('gpu_power_w',2000), ('logical_cores',4096), ('total_ram_mb',1048576)]:
        if key in hw: cleaned[key] = bounded(hw[key], 0, maximum)
    if 'plugged_in' in hw:
        if type(hw['plugged_in']) is not bool: raise ValueError('Invalid charging flag.')
        cleaned['plugged_in'] = hw['plugged_in']
    canonical = dict(result, sample_id=sid, collected_at=collected.isoformat(), hardware=cleaned)
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',',':')).encode()).hexdigest()
    return result, sid, collected.replace(tzinfo=None), cleaned, fingerprint
