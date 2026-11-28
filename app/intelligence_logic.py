"""Transparent, deterministic carbon intelligence calculations."""
from datetime import timedelta
import math
from statistics import mean

ACTIVITY_TYPES = {
    'computing': 'Coding / computing', 'browsing': 'Web browsing',
    'streaming': 'Video / audio streaming', 'downloads': 'Downloads / uploads',
    'cloud': 'Remote cloud workload', 'other': 'Other digital activity',
}

def energy_estimate(watts, hours):
    watts, hours = float(watts), float(hours)
    if not (math.isfinite(watts) and math.isfinite(hours)
            and 0 < watts <= 10000 and 0 < hours <= 24):
        raise ValueError('Use valid average watts and hours (maximum 24 hours).')
    return watts * hours / 1000

def analyse_days(daily, today):
    """daily maps UTC date -> recorded kg CO2e; missing is not zero."""
    recent = [daily.get(today-timedelta(days=i)) for i in range(7,0,-1)]
    previous = [daily.get(today-timedelta(days=i)) for i in range(14,7,-1)]
    covered = sum(x is not None for x in recent)
    baseline_covered = sum(x is not None for x in previous)
    current_total = sum(x for x in recent if x is not None)
    baseline_total = sum(x for x in previous if x is not None)
    change = score = None
    if covered == baseline_covered == 7 and baseline_total > 0:
        change = (current_total / baseline_total - 1) * 100
        score = round(max(0, min(100, 50 - change / 2)))
    forecast = mean(recent)*7 if covered == 7 else None
    anchor = today if today in daily else today-timedelta(days=1)
    streak = 0
    while anchor in daily:
        streak += 1
        anchor -= timedelta(days=1)
    return dict(current_total=current_total, baseline_total=baseline_total,
                covered=covered, baseline_covered=baseline_covered, change=change,
                score=score, forecast=forecast, streak=streak, recorded_days=len(daily))

def recommendations(categories, analysis):
    tips = []
    total = sum(categories.values())
    if total > 0:
        key = max(categories, key=categories.get)
        suggestions = {
            'computing': 'Review high-CPU workloads, close unused applications, and compare efficient algorithms.',
            'streaming': 'Choose an appropriate streaming resolution and avoid unnecessary autoplay.',
            'browsing': 'Close unused tabs and avoid unnecessary background activity.',
            'downloads': 'Avoid repeated downloads and unnecessary transfers.',
            'cloud': 'Stop idle cloud workloads and right-size allocated resources.',
            'device_estimate': 'Review operating hours and average power of your registered electronic devices.',
        }
        tips.append(f"Largest recorded category: {key.replace('_',' ')} ({categories[key]/total:.1%} of recorded carbon). " + suggestions.get(key, 'Review the underlying power and usage duration.'))
    if analysis['change'] is not None:
        tips.append(f"Your recorded carbon changed by {analysis['change']:+.1f}% versus the previous complete seven-day period. Check that both periods cover comparable device use.")
    else:
        tips.append('Record activity on each day of two consecutive weeks to unlock a personal benchmark and Green Score.')
    tips.append('Avoid duplicate records for energy already included in your laptop agent. Prefer calibrated power profiles.')
    return tips
