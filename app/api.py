import secrets, hashlib
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from . import db, limiter, csrf
from .models import Device
from .services import record_activity

api = Blueprint("api", __name__, url_prefix="/api")
def digest(token): return hashlib.sha256(token.encode("utf-8")).hexdigest()

@api.post("/devices/enroll")
@login_required
@limiter.limit("10 per hour")
def enroll():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    platform = str(data.get("platform", "")).strip().lower()
    if not name or len(name) > 100 or platform not in ("windows", "linux", "macos"):
        return jsonify(error="Provide a device name and supported platform."), 400
    token = secrets.token_urlsafe(36)
    device = Device(user_id=current_user.id, name=name, platform=platform, token_hash=digest(token))
    db.session.add(device)
    db.session.commit()
    return jsonify(device_id=device.id, token=token, message="Store this token securely. It is shown only once."), 201

@api.post("/telemetry")
@csrf.exempt  # Device bearer token is the authentication mechanism for headless agents.
@limiter.limit("120 per minute")
def telemetry():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify(error="Device token required."), 401
    token = auth[7:].strip()
    if not token or len(token) > 256:
        return jsonify(error="Invalid device token."), 401
    device = Device.query.filter_by(token_hash=digest(token), active=True).first()
    if not device:
        return jsonify(error="Invalid or revoked device token."), 401
    data = request.get_json(silent=True) or {}
    try:
        duration = float(data.get("duration_seconds", 0))
        cpu = float(data.get("cpu_percent", 0))
        memory = float(data.get("memory_mb", 0))
        energy = float(data.get("energy_kwh", 0))
        if not (0 <= duration <= 86400 and 0 <= cpu <= 100 and 0 <= memory <= 1048576 and 0 <= energy <= 100):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify(error="Telemetry values are outside allowed ranges."), 400
    device.last_seen = datetime.utcnow()
    row = record_activity(device.user_id, "computing", energy, "Monitoring agent telemetry", "estimated",
                          device.id, duration, cpu, memory)
    return jsonify(status="accepted", activity_id=row.id, carbon_kg=row.carbon_kg), 201

@api.get("/agent/status")
@login_required
def agent_status():
    devices = Device.query.filter_by(user_id=current_user.id).all()
    return jsonify(devices=[{"id": d.id, "name": d.name, "platform": d.platform, "active": d.active,
                             "last_seen": d.last_seen.isoformat() if d.last_seen else None} for d in devices])
