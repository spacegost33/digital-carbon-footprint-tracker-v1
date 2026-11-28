"""Pure, transparent calculations for device analytics and savings scenarios."""
from datetime import timedelta
import math

PERIODS = {'24h': 1, '7d': 7, '30d': 30}
DEFAULT_TARIFF = 8.0  # Illustrative INR/kWh, not an official tariff.


def number(value, low, high):
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'Expected a finite value between {low:g} and {high:g}.')
    return value


def average_watts(energy_kwh, seconds):
    # Older agents reported zero when energy was not collected.
    if energy_kwh is None or seconds is None or energy_kwh <= 0 or seconds <= 0:
        return None
    result = energy_kwh * 3_600_000 / seconds
    return result if math.isfinite(result) else None


def device_status(active, last_seen, now):
    if not active:
        return 'Revoked'
    if last_seen is None:
        return 'Never reported'
    if timedelta(0) <= now - last_seen <= timedelta(minutes=10):
        return 'Recently reporting'
    return 'Stale / offline'


def savings(watts, hours, reduced_hours, days, tariff, factor):
    watts = number(watts, 0.001, 10000)
    hours = number(hours, 0, 24)
    reduced_hours = number(reduced_hours, 0, hours)
    days = int(days)
    if not 1 <= days <= 365:
        raise ValueError('Days must be between 1 and 365.')
    tariff = number(tariff, 0, 1000)
    factor = number(factor, 0, 5)
    baseline = watts * hours * days / 1000
    proposed = watts * (hours - reduced_hours) * days / 1000
    saved = watts * reduced_hours * days / 1000
    return dict(baseline=baseline, proposed=proposed, energy=saved,
                carbon=saved * factor, cost=saved * tariff,
                percent=100 * reduced_hours / hours if hours else 0)


def chart_points(samples, field, max_value=None):
    """Position points by actual receipt time, omit missing observations."""
    if not samples:
        return {'points': [], 'ceiling': 0, 'start': '', 'end': ''}
    start, end = samples[0]['time'], samples[-1]['time']
    span = (end-start).total_seconds()
    valid = [(s['time'], s[field]) for s in samples if s[field] is not None and math.isfinite(s[field]) and s[field] >= 0]
    ceiling = max_value if max_value is not None else max([v for _, v in valid] + [1])
    pts = [{'x': round(28 + 304*((t-start).total_seconds()/span if span else .5), 2),
            'y': round(105 - 85*min(v/ceiling, 1), 2), 'value': v,
            'label': t.strftime('%d %b %H:%M:%S UTC')} for t,v in valid]
    return {'points': pts, 'ceiling': ceiling, 'start': start.strftime('%d %b %H:%M'), 'end': end.strftime('%d %b %H:%M')}
