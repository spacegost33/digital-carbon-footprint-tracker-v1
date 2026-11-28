from datetime import datetime, timedelta
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from . import db, limiter
from .models import Activity, Goal, Device
from .services import active_factor, record_activity
from .intelligence_logic import ACTIVITY_TYPES, energy_estimate, analyse_days, recommendations

intelligence = Blueprint('intelligence', __name__)

@intelligence.get('/intelligence')
@login_required
def overview():
    today = datetime.utcnow().date()
    grouped = db.session.query(func.date(Activity.created_at), func.sum(Activity.carbon_kg)).filter(
        Activity.user_id == current_user.id).group_by(func.date(Activity.created_at)).all()
    daily = {}
    for day, carbon in grouped:
        if isinstance(day, str): day = datetime.strptime(day, '%Y-%m-%d').date()
        daily[day] = float(carbon or 0)
    analysis = analyse_days(daily, today)
    since = datetime.combine(today-timedelta(days=30), datetime.min.time())
    categories = dict((name, float(carbon or 0)) for name, carbon in db.session.query(
        Activity.category, func.sum(Activity.carbon_kg)).filter(Activity.user_id == current_user.id,
        Activity.created_at >= since).group_by(Activity.category).all())
    device_count = Device.query.filter_by(user_id=current_user.id, active=True).count()
    challenges = [
        ('Log today', 1 if today in daily else 0, 1),
        ('Record activity on seven consecutive days', min(analysis['streak'], 7), 7),
        ('Enroll a monitoring device', min(device_count, 1), 1),
    ]
    badges = [('First record', bool(daily)), ('Three-day tracker', analysis['streak'] >= 3),
              ('Seven-day tracker', analysis['streak'] >= 7), ('Device connected', device_count > 0),
              ('Lower recorded footprint', analysis['change'] is not None and analysis['change'] < 0)]
    goals = Goal.query.filter(Goal.user_id == current_user.id, Goal.end_date >= today).order_by(Goal.end_date).all()
    budgets = []
    for g in goals:
        used = sum(v for d,v in daily.items() if g.start_date <= d <= g.end_date)
        budgets.append(dict(title=g.title, target=g.target_kg, used=used, end=g.end_date))
    return render_template('intelligence.html', analysis=analysis, categories=categories,
        tips=recommendations(categories, analysis), profiles=ACTIVITY_TYPES,
        factor=active_factor(current_user.region), challenges=challenges, badges=badges, budgets=budgets)

@intelligence.post('/intelligence/activity')
@login_required
@limiter.limit('30 per hour')
def log_activity():
    try:
        category = request.form.get('category', '')
        if category not in ACTIVITY_TYPES or request.form.get('no_overlap') != 'yes':
            raise ValueError('Confirm that this energy is not already tracked.')
        watts = float(request.form.get('watts', ''))
        hours = float(request.form.get('hours', ''))
        label = request.form.get('description', '').strip()
        if len(label) > 120: raise ValueError('Description is too long.')
        energy = energy_estimate(watts, hours)
        row = record_activity(current_user.id, category, energy,
            f'{label or ACTIVITY_TYPES[category]} | {watts:g} W x {hours:g} h', 'estimated', duration_seconds=hours*3600)
        flash(f'Activity saved: {energy:.6f} kWh, {row.carbon_kg:.6f} kg CO2e.', 'success')
    except (ValueError, TypeError, OverflowError) as exc:
        flash('Invalid activity. Enter valid power, duration and confirm no duplicate energy.', 'error')
    return redirect(url_for('intelligence.overview'))

@intelligence.post('/intelligence/budget')
@login_required
@limiter.limit('10 per hour')
def budget():
    try:
        period = int(request.form.get('period', ''))
        target = float(request.form.get('target', ''))
        if period not in (1, 7) or not 0 < target <= 100000: raise ValueError
        today = datetime.utcnow().date()
        title = 'Daily carbon budget' if period == 1 else 'Weekly carbon budget'
        db.session.add(Goal(user_id=current_user.id, title=title, target_kg=target,
                            start_date=today, end_date=today+timedelta(days=period-1)))
        db.session.commit()
        flash('Carbon budget created.', 'success')
    except (ValueError, TypeError, OverflowError):
        flash('Choose a daily or weekly budget and valid positive target.', 'error')
    return redirect(url_for('intelligence.overview'))
