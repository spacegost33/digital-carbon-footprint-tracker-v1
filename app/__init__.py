import os
from flask import Flask, jsonify
from sqlalchemy import text
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# Extensions are initialized by the application factory.
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per hour"])

def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    database_url = os.getenv("DATABASE_URL", "sqlite:///carbontrack.sqlite3")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    secret = os.getenv("SECRET_KEY")
    if not secret and os.getenv("FLASK_ENV", "production") == "production":
        raise RuntimeError("SECRET_KEY must be configured in the hosting environment.")
    app.config.update(
        SECRET_KEY=secret or "local-development-only-change-me",
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        WTF_CSRF_TIME_LIMIT=3600,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        PERMANENT_SESSION_LIFETIME=__import__("datetime").timedelta(days=7),
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "web.login"
    login_manager.login_message_category = "info"
    csrf.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    from . import models
    from .routes import web
    from .api import api
    app.register_blueprint(web)
    app.register_blueprint(api)
    from .intelligence import intelligence
    app.register_blueprint(intelligence)

    @app.get("/health")
    def health():
        # Render only receives healthy when the application can reach its database.
        try:
            db.session.execute(text("SELECT 1"))
            db.session.remove()
            return jsonify(status="ok", service="CarbonTrack", database="connected"), 200
        except Exception:
            db.session.rollback()
            app.logger.exception("Health check database connection failed")
            return jsonify(status="unavailable", service="CarbonTrack"), 503

    @app.context_processor
    def inject_globals():
        from flask_wtf.csrf import generate_csrf
        return {"app_name": "CarbonTrack", "csrf_token_value": generate_csrf()}

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request_is_https():
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    with app.app_context():
        # create_all is additive: it creates missing tables but does not drop or rewrite
        # existing tables/records. Model changes still require reviewed migrations.
        db.create_all()
        if not models.EmissionFactor.query.filter_by(region="IN-KA", active=True).first():
            db.session.add(models.EmissionFactor(
                region="IN-KA", name="Karnataka grid starter estimate", kg_per_kwh=0.70,
                source="Starter placeholder; replace with the applicable official factor",
                version="starter-1", active=True))
            db.session.commit()
    return app

def request_is_https():
    from flask import request
    return request.is_secure

@login_manager.user_loader
def load_user(user_id):
    from .models import User
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
