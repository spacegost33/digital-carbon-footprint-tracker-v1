"""Additive tables; existing Activity rows and schema remain intact."""
from datetime import datetime
from . import db
from .models import EmissionFactor

CEA_VERSION = 'CEA-v22-FY2025-26'
CEA_VALUE = 0.675
CEA_SOURCE = 'CEA CO2 baseline v22 FY2025-26; Vidyut Vahini Oct 2026 p13: https://www.cea.nic.in/whats-new/file?mode=view&path=%2Fhome%2Fcea_website%2Freports%2Fgeneral%2Fen%2FVidyut+vahini.pdf'

class TelemetryReceipt(db.Model):
    __tablename__ = 'telemetry_receipt'
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), primary_key=True)
    sample_id = db.Column(db.String(36), primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=False, unique=True)
    fingerprint = db.Column(db.String(64), nullable=False)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    hardware = db.Column(db.JSON, nullable=False, default=dict)

class ActivityFactor(db.Model):
    __tablename__ = 'activity_factor'
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), primary_key=True)
    factor_id = db.Column(db.Integer, db.ForeignKey('emission_factor.id'))
    region = db.Column(db.String(40), nullable=False)
    basis = db.Column(db.String(40), nullable=False)
    value = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(240), nullable=False)
    version = db.Column(db.String(40), nullable=False)

class ChatQuota(db.Model):
    __tablename__ = 'chat_quota'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    day = db.Column(db.Date, primary_key=True)
    used = db.Column(db.Integer, nullable=False, default=0)


class ChatGlobalQuota(db.Model):
    __tablename__ = 'chat_global_quota'
    day = db.Column(db.Date, primary_key=True)
    used = db.Column(db.Integer, nullable=False, default=0)


def seed_factor(connection):
    """Run inside the same startup transaction/advisory lock as create_all."""
    from sqlalchemy import select, update, insert
    table = EmissionFactor.__table__
    # Retire only our old placeholder, retain administrator-created factors.
    connection.execute(update(table).where(table.c.version == 'starter-1').values(active=False))
    if connection.execute(select(table.c.id).where(table.c.region == 'IN', table.c.version == CEA_VERSION)).first() is None:
        active = connection.execute(select(table.c.id).where(table.c.region == 'IN', table.c.active.is_(True))).first()
        connection.execute(insert(table).values(region='IN', name='India national grid (CEA)', kg_per_kwh=CEA_VALUE,
            source=CEA_SOURCE, version=CEA_VERSION, active=not bool(active), created_at=datetime.utcnow()))


def factor_details(region):
    region = (region or 'IN').upper()
    row = EmissionFactor.query.filter_by(region=region, active=True).order_by(EmissionFactor.created_at.desc(), EmissionFactor.id.desc()).first()
    basis = 'exact-region'
    if row is None:
        row = EmissionFactor.query.filter_by(region='IN', active=True).order_by(EmissionFactor.created_at.desc(), EmissionFactor.id.desc()).first()
        basis = 'india-national' if region.startswith('IN-') or region == 'IN' else 'india-proxy-unverified'
    if row is None:
        return dict(id=None, region=region, basis='india-national' if region=='IN' or region.startswith('IN-') else 'india-proxy-unverified', value=CEA_VALUE, version=CEA_VERSION, source=CEA_SOURCE)
    return dict(id=row.id, region=region, basis=basis, value=float(row.kg_per_kwh), version=row.version, source=row.source)
