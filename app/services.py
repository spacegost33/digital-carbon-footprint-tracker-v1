from datetime import datetime, timedelta
import math
from sqlalchemy import func
from . import db
from .models import Activity, Achievement, User
from .reliability import ActivityFactor, factor_details


def active_factor(region):
    return factor_details(region)['value']


def record_activity(user_id, category, energy_kwh, description='', measurement_type='estimated', device_id=None, duration_seconds=0, cpu_percent=None, memory_mb=None, *, created_at=None, commit=True):
    if not math.isfinite(energy_kwh) or not 0 <= energy_kwh <= 10000:
        raise ValueError('Invalid energy.')
    # Serializes achievement creation and concurrent activity writes per account in Postgres.
    owner = User.query.filter_by(id=user_id).populate_existing().with_for_update().first()
    if owner is None: raise ValueError('Unknown owner.')
    f = factor_details(owner.region)
    if f['basis'] == 'india-proxy-unverified':
        raise ValueError('Set an applicable region with a registered emission factor before recording energy.')
    row = Activity(user_id=user_id, category=category, description=description[:240], energy_kwh=energy_kwh,
                   carbon_kg=energy_kwh*f['value'], measurement_type=measurement_type, device_id=device_id,
                   duration_seconds=duration_seconds, cpu_percent=cpu_percent, memory_mb=memory_mb,
                   created_at=created_at or datetime.utcnow())
    db.session.add(row); db.session.flush()
    db.session.add(ActivityFactor(activity_id=row.id, factor_id=f['id'], region=f['region'], basis=f['basis'], value=f['value'], source=f['source'], version=f['version']))
    total = db.session.query(func.coalesce(func.sum(Activity.carbon_kg), 0)).filter(Activity.user_id == user_id).scalar() or 0
    if total >= 1 and not Achievement.query.filter_by(user_id=user_id, code='first_kg').first():
        db.session.add(Achievement(user_id=user_id, code='first_kg', title='Carbon data contributor'))
    if commit: db.session.commit()
    return row


def totals(user_id, days=30):
    since = datetime.utcnow() - timedelta(days=days)
    energy, carbon, count, measured = db.session.query(func.coalesce(func.sum(Activity.energy_kwh),0), func.coalesce(func.sum(Activity.carbon_kg),0), func.count(Activity.id), func.count(Activity.id).filter(Activity.measurement_type=='measured')).filter(Activity.user_id==user_id, Activity.created_at>=since).one()
    return {'carbon': round(float(carbon), 6), 'energy': round(float(energy), 6), 'count': count, 'estimated': count-measured, 'measured': measured}
