from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from . import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    region = db.Column(db.String(40), default="IN-KA")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    platform = db.Column(db.String(40), nullable=False)
    token_hash = db.Column(db.String(128), nullable=False, unique=True)
    last_seen = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"))
    category = db.Column(db.String(40), nullable=False)
    description = db.Column(db.String(240), default="")
    energy_kwh = db.Column(db.Float, nullable=False, default=0)
    carbon_kg = db.Column(db.Float, nullable=False, default=0)
    measurement_type = db.Column(db.String(24), default="estimated")
    duration_seconds = db.Column(db.Float, default=0)
    cpu_percent = db.Column(db.Float)
    memory_mb = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class EmissionFactor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    kg_per_kwh = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(240), nullable=False)
    version = db.Column(db.String(40), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    target_kg = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.Date, default=date.today)
    end_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    code = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "code", name="uq_user_achievement"),)
