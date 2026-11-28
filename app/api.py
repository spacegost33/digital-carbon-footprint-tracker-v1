import secrets, hashlib
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from . import db, limiter, csrf
from .models import Device, User, Activity
from .services import record_activity
from .reliability import TelemetryReceipt
from .telemetry_validation import validate

api = Blueprint('api', __name__, url_prefix='/api')

def digest(token): return hashlib.sha256(token.encode('utf-8')).hexdigest()

def token_key():
    auth = request.headers.get('Authorization','')
    # Existing default/IP limit still applies separately to unauthenticated traffic.
    return digest(auth[:300]) if auth.startswith('Bearer ') else 'anonymous:' + (request.remote_addr or '')

@api.post('/devices/enroll')
@login_required
@limiter.limit('10 per hour')
def enroll():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('name'), str) or not isinstance(data.get('platform'), str):
        return jsonify(error='Provide a device name and supported platform.'), 400
    name, platform = data['name'].strip(), data['platform'].strip().lower()
    if not name or len(name)>100 or platform not in ('windows','linux','macos'):
        return jsonify(error='Provide a device name and supported platform.'), 400
    User.query.filter_by(id=current_user.id).with_for_update().first()
    if Device.query.filter_by(user_id=current_user.id, active=True).count() >= 50:
        return jsonify(error='Revoke an unused device before enrolling another.'), 409
    token = secrets.token_urlsafe(36)
    device = Device(user_id=current_user.id, name=name, platform=platform, token_hash=digest(token))
    db.session.add(device); db.session.commit()
    return jsonify(device_id=device.id, token=token, message='Store this token securely. It is shown only once.'), 201

@api.post('/telemetry')
@csrf.exempt
@limiter.limit('120 per minute')
@limiter.limit('60 per minute', key_func=token_key)
def telemetry():
    auth = request.headers.get('Authorization','')
    if not auth.startswith('Bearer ') or not 1 <= len(auth[7:].strip()) <= 256:
        return jsonify(error='Device token required.'), 401
    token_hash = digest(auth[7:].strip())
    device = Device.query.filter_by(token_hash=token_hash, active=True).first()
    if not device: return jsonify(error='Invalid or revoked device token.'), 401
    if request.content_length is not None and request.content_length > 16384:
        return jsonify(error='Telemetry payload too large.'), 413
    try:
        values, sid, collected, hw, fingerprint = validate(request.get_json(silent=True), datetime.now(timezone.utc))
    except (ValueError, TypeError, KeyError, OverflowError):
        return jsonify(error='Invalid telemetry values, timestamp or protocol.'), 400
    try:
        owner_id, device_id = device.user_id, device.id
        User.query.filter_by(id=owner_id).with_for_update().first()
        device = Device.query.filter_by(id=device_id, active=True).populate_existing().with_for_update().first()
        if not device: return jsonify(error='Invalid or revoked device token.'), 401
        if sid:
            prior = db.session.get(TelemetryReceipt, (device_id, sid))
            if prior:
                if prior.fingerprint != fingerprint:
                    return jsonify(error='Sample ID conflicts with an earlier observation.'), 409
                row = db.session.get(Activity, prior.activity_id)
                device.last_seen = datetime.utcnow(); db.session.commit()
                return jsonify(status='duplicate', sample_id=sid, activity_id=row.id, carbon_kg=row.carbon_kg), 200
        # Store original observation time, not retry time. Tiny future clock skew is retained.
        device.last_seen = datetime.utcnow()
        row = record_activity(owner_id, 'computing', values['energy_kwh'], 'Monitoring agent telemetry', 'estimated', device_id,
                              values['duration_seconds'], values['cpu_percent'], values['memory_mb'], created_at=collected, commit=False)
        if sid:
            db.session.add(TelemetryReceipt(device_id=device_id, sample_id=sid, activity_id=row.id, fingerprint=fingerprint, hardware=hw))
        db.session.commit()
        return jsonify(status='accepted', sample_id=sid, activity_id=row.id, carbon_kg=row.carbon_kg), 201
    except ValueError:
        db.session.rollback()
        return jsonify(error='Account region needs an applicable emission factor; update Settings and retry.'), 503
    except IntegrityError:
        db.session.rollback()
        # Do not acknowledge a write that failed; safe retry with the original UUID.
        return jsonify(error='Concurrent write; retry original sample.'), 503
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error='Database temporarily unavailable; retry.'), 503

@api.get('/agent/status')
@login_required
def agent_status():
    devices = Device.query.filter_by(user_id=current_user.id).all()
    return jsonify(devices=[dict(id=d.id,name=d.name,platform=d.platform,active=d.active,last_seen=d.last_seen.isoformat() if d.last_seen else None) for d in devices])
