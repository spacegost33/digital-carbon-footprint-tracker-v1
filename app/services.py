from datetime import datetime, timedelta
from sqlalchemy import func
from . import db
from .models import Activity, EmissionFactor, Achievement, User

def active_factor(region):
    factor = EmissionFactor.query.filter_by(region=region, active=True).order_by(EmissionFactor.created_at.desc()).first()
    if not factor:
        factor = EmissionFactor.query.filter_by(active=True).order_by(EmissionFactor.created_at.desc()).first()
    return factor.kg_per_kwh if factor else 0.70

def record_activity(user_id, category, energy_kwh, description="", measurement_type="estimated", device_id=None, duration_seconds=0, cpu_percent=None, memory_mb=None):
    owner = db.session.get(User, user_id)
    factor = active_factor(owner.region if owner else "IN-KA")
    row = Activity(user_id=user_id, category=category, description=description[:240], energy_kwh=energy_kwh,
                   carbon_kg=energy_kwh * factor, measurement_type=measurement_type, device_id=device_id,
                   duration_seconds=duration_seconds, cpu_percent=cpu_percent, memory_mb=memory_mb)
    db.session.add(row)
    db.session.flush()
    total = db.session.query(func.coalesce(func.sum(Activity.carbon_kg), 0)).filter(Activity.user_id == user_id).scalar() or 0
    if total >= 1 and not Achievement.query.filter_by(user_id=user_id, code="first_kg").first():
        db.session.add(Achievement(user_id=user_id, code="first_kg", title="Carbon data contributor"))
    db.session.commit()
    return row

def totals(user_id, days=30):
    since = datetime.utcnow() - timedelta(days=days)
    rows = Activity.query.filter(Activity.user_id == user_id, Activity.created_at >= since).all()
    return {"carbon": round(sum(x.carbon_kg for x in rows), 3), "energy": round(sum(x.energy_kwh for x in rows), 3),
            "count": len(rows), "estimated": sum(x.measurement_type != "measured" for x in rows),
            "measured": sum(x.measurement_type == "measured" for x in rows)}
