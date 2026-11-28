"""Device analytics and energy optimizer, using existing CarbonTrack tables."""
from datetime import datetime, timedelta
from flask import Blueprint, abort, make_response, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func
from . import db
from .models import Activity, Device
from .services import active_factor
from .energy_logic import PERIODS, DEFAULT_TARIFF, number, average_watts, device_status, savings, chart_points

energy_tools = Blueprint('energy_tools', __name__)


def private_response(template, **context):
    response = make_response(render_template(template, **context))
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def tariff_value():
    try:
        return number(request.args.get('tariff', DEFAULT_TARIFF), 0, 1000)
    except (ValueError, TypeError, OverflowError):
        abort(400, description='Tariff must be between 0 and 1000 INR/kWh.')


def device_context():
    uid = current_user.id
    now = datetime.utcnow()
    period = request.args.get('period', '24h')
    if period not in PERIODS:
        abort(400, description='Invalid time range.')
    tariff = tariff_value()
    since = now - timedelta(days=PERIODS[period])
    devices = Device.query.filter_by(user_id=uid).order_by(Device.created_at.desc(), Device.id.desc()).all()
    requested = request.args.get('device', '')
    if requested:
        try:
            selected_id = int(requested)
        except (ValueError, TypeError):
            abort(404)
        selected = next((d for d in devices if d.id == selected_id), None)
        if selected is None:
            abort(404)
    else:
        selected = devices[0] if devices else None
    base = Activity.query.filter(Activity.user_id == uid, Activity.created_at >= since, Activity.created_at <= now)
    totals = base.with_entities(func.coalesce(func.sum(Activity.energy_kwh),0), func.coalesce(func.sum(Activity.carbon_kg),0), func.count(Activity.id)).one()
    grouped = base.filter(Activity.device_id.isnot(None)).with_entities(
        Activity.device_id, func.sum(Activity.energy_kwh), func.sum(Activity.carbon_kg), func.sum(Activity.duration_seconds), func.count(Activity.id)
    ).group_by(Activity.device_id).all()
    by_device = {r[0]: r[1:] for r in grouped}
    comparisons = []
    for d in devices:
        e,c,seconds,count = by_device.get(d.id, (0,0,0,0))
        comparisons.append(dict(id=d.id, name=d.name, platform=d.platform, status=device_status(d.active,d.last_seen,now),
            energy=float(e or 0), carbon=float(c or 0), runtime=float(seconds or 0)/3600, count=count, cost=float(e or 0)*tariff))
    comparisons.sort(key=lambda r: r['energy'], reverse=True)
    # Manual device estimates have no device_id. Group by the recorded display name,
    # not by an invented hardware identity. All rows are still counted only once.
    manual_rows = base.filter(Activity.device_id.is_(None), Activity.category=='device_estimate').with_entities(
        Activity.description, func.sum(Activity.energy_kwh), func.sum(Activity.carbon_kg), func.count(Activity.id)
    ).group_by(Activity.description).all()
    manual_groups = {}
    for desc,e,c,count in manual_rows:
        name = (desc or 'Unnamed device').rsplit(' | ',1)[0]
        g = manual_groups.setdefault(name, dict(name=name,energy=0.,carbon=0.,count=0,cost=0.))
        g['energy'] += float(e or 0); g['carbon'] += float(c or 0); g['count'] += count
        g['cost'] = g['energy'] * tariff
    manual = sorted(manual_groups.values(), key=lambda r:r['energy'], reverse=True)
    latest = None; samples = []; selected_stats = None
    if selected:
        selected_stats = next(r for r in comparisons if r['id']==selected.id)
        latest_row = Activity.query.filter_by(user_id=uid, device_id=selected.id).order_by(Activity.created_at.desc(), Activity.id.desc()).first()
        if latest_row:
            latest = dict(time=latest_row.created_at.strftime('%d %b %Y %H:%M:%S UTC'),
                cpu=latest_row.cpu_percent, ram=latest_row.memory_mb/1024 if latest_row.memory_mb is not None else None,
                power=average_watts(latest_row.energy_kwh, latest_row.duration_seconds))
        rows = base.filter(Activity.device_id==selected.id).order_by(Activity.created_at.desc(),Activity.id.desc()).limit(48).all()
        for a in reversed(rows):
            samples.append(dict(time=a.created_at, cpu=a.cpu_percent, ram=a.memory_mb/1024 if a.memory_mb is not None else None,
                power=average_watts(a.energy_kwh,a.duration_seconds), energy=a.energy_kwh, carbon=a.carbon_kg))
    charts = [('CPU utilization','%',chart_points(samples,'cpu',100)), ('RAM used','GiB',chart_points(samples,'ram')), ('Estimated average power','W',chart_points(samples,'power'))]
    auto_energy = sum(r['energy'] for r in comparisons)
    manual_energy = sum(r['energy'] for r in manual)
    return dict(devices=devices, selected=selected, selected_stats=selected_stats, comparisons=comparisons, manual=manual,
        latest=latest, samples=list(reversed(samples)), charts=charts, period=period, periods=PERIODS, tariff=tariff,
        total_energy=float(totals[0]), total_carbon=float(totals[1]), total_count=totals[2], total_cost=float(totals[0])*tariff,
        auto_energy=auto_energy, manual_energy=manual_energy, other_energy=float(totals[0])-auto_energy-manual_energy,
        refreshed=now.strftime('%d %b %Y %H:%M:%S UTC'))


@energy_tools.get('/device-intelligence')
@login_required
def devices():
    return private_response('device_intelligence.html', **device_context())


@energy_tools.get('/device-intelligence/snapshot')
@login_required
def snapshot():
    return private_response('_device_snapshot.html', **device_context())


@energy_tools.get('/energy-optimizer')
@login_required
def optimizer():
    tariff = tariff_value()
    factor = active_factor(current_user.region)
    inputs = {k: request.args.get(k, default) for k,default in [('watts','45'),('hours','8'),('reduced_hours','2'),('days','30')]}
    result = None; error = None
    try:
        result = savings(inputs['watts'],inputs['hours'],inputs['reduced_hours'],inputs['days'],tariff,factor)
    except (ValueError, TypeError, OverflowError) as exc:
        error = str(exc)
    return private_response('energy_optimizer.html', tariff=tariff, factor=factor, inputs=inputs, result=result, error=error)
