from datetime import datetime, date, timedelta
from io import BytesIO, StringIO
import csv, re
from statistics import mean
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, abort
from flask_login import login_user, logout_user, login_required, current_user
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from . import db, limiter
from .models import User, Activity, Device, Goal, Achievement, EmissionFactor
from .services import record_activity, totals, active_factor

web = Blueprint("web", __name__)
CATEGORIES = {"computing", "browsing", "streaming", "downloads", "cloud", "other"}

@web.get("/")
def home():
    return redirect(url_for("web.dashboard")) if current_user.is_authenticated else render_template("landing.html")

@web.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(name) < 2 or len(name) > 100 or len(email) > 180 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not 10 <= len(password) <= 128:
            flash("Enter a valid name and email. Passwords must be 10–128 characters.", "error")
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
                login_user(user)
                return redirect(url_for("web.dashboard"))
            except IntegrityError:
                db.session.rollback()
                flash("An account with that email already exists.", "error")
    return render_template("auth.html", mode="Create account")

@web.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(url_for("web.dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("auth.html", mode="Sign in")

@web.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("web.home"))

@web.get("/dashboard")
@login_required
def dashboard():
    stats = totals(current_user.id, 30)
    device_records = Activity.query.filter(
        Activity.user_id == current_user.id,
        Activity.device_id.isnot(None),
        Activity.created_at >= (
            datetime.utcnow()
            - timedelta(days=30)
        )
    )

    device_energy = device_records.with_entities(
        func.coalesce(
            func.sum(Activity.energy_kwh), 0
        )
    ).scalar()

    device_carbon = device_records.with_entities(
        func.coalesce(
            func.sum(Activity.carbon_kg), 0
        )
    ).scalar()

    device_runtime = device_records.with_entities(
        func.coalesce(
            func.sum(Activity.duration_seconds), 0
        )
    ).scalar()

    
    recent = Activity.query.filter_by(user_id=current_user.id).order_by(Activity.created_at.desc()).limit(8).all()
    devices = Device.query.filter_by(user_id=current_user.id, active=True).count()
    daily = []
    for offset in range(6, -1, -1):
        day = date.today() - timedelta(days=offset)
        value = db.session.query(func.coalesce(func.sum(Activity.carbon_kg), 0)).filter(
            Activity.user_id == current_user.id, func.date(Activity.created_at) == day).scalar() or 0
        daily.append({"day": day.strftime("%a"), "value": round(float(value), 3)})


    return render_template(
        "dashboard.html",

        stats=stats,
        recent=recent,
        devices=devices,
        daily=daily,

        factor=active_factor(
            current_user.region
        ),

        device_energy=round(
            float(device_energy), 4
        ),

        device_carbon=round(
            float(device_carbon), 4
        ),

        device_runtime=round(
            float(device_runtime) / 3600, 2
        )
    )

@web.route("/activities", methods=["GET", "POST"])
@login_required
def activities():
    if request.method == "POST":
        try:
            category = request.form.get("category", "").strip()
            energy = float(request.form.get("energy_kwh", ""))
            description = request.form.get("description", "").strip()
            if category not in CATEGORIES or not 0 < energy <= 10000 or len(description) > 240:
                raise ValueError
            record_activity(current_user.id, category, energy, description, "estimated")
            flash("Activity recorded. The energy value is labelled as an estimate.", "success")
            return redirect(url_for("web.activities"))
        except (ValueError, TypeError):
            flash("Choose a category and enter energy between 0 and 10,000 kWh.", "error")
    rows = Activity.query.filter_by(user_id=current_user.id).order_by(Activity.created_at.desc()).limit(100).all()
    return render_template("activities.html", rows=rows)

@web.get("/devices")
@login_required
def devices():
    rows = Device.query.filter_by(user_id=current_user.id).order_by(Device.created_at.desc()).all()
    return render_template("devices.html", devices=rows)

@web.post("/devices/<int:device_id>/revoke")
@login_required
def revoke_device(device_id):
    device = Device.query.filter_by(id=device_id, user_id=current_user.id).first_or_404()
    device.active = False
    db.session.commit()
    flash("Device access revoked.", "success")
    return redirect(url_for("web.devices"))

@web.get("/analytics")
@login_required
def analytics():
    weekly, monthly = totals(current_user.id, 7), totals(current_user.id, 30)
    values = []
    for offset in range(13, -1, -1):
        day = date.today() - timedelta(days=offset)
        value = db.session.query(func.coalesce(func.sum(Activity.carbon_kg), 0)).filter(
            Activity.user_id == current_user.id, func.date(Activity.created_at) == day).scalar() or 0
        values.append(float(value))
    observed = sum(value > 0 for value in values)
    forecast = None
    if observed >= 7:
        xs = list(range(len(values))); xbar = mean(xs); ybar = mean(values)
        denom = sum((x - xbar) ** 2 for x in xs) or 1
        slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, values)) / denom
        forecast = round(max(0, ybar + slope * 7), 3)
    return render_template("analytics.html", daily=weekly, monthly=monthly, forecast=forecast, observed=observed)

@web.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    if request.method == "POST":
        try:
            title = request.form.get("title", "").strip()
            target = float(request.form.get("target_kg", ""))
            end = datetime.strptime(request.form.get("end_date", ""), "%Y-%m-%d").date()
            if not title or len(title) > 120 or not 0 < target <= 100000 or end <= date.today():
                raise ValueError
            db.session.add(Goal(user_id=current_user.id, title=title, target_kg=target, end_date=end))
            db.session.commit()
            flash("Goal created.", "success")
            return redirect(url_for("web.goals"))
        except (ValueError, TypeError):
            flash("Check the goal details and choose a future end date.", "error")
    rows = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.end_date).all()
    for goal in rows:
        consumed = db.session.query(func.coalesce(func.sum(Activity.carbon_kg), 0)).filter(
            Activity.user_id == current_user.id,
            func.date(Activity.created_at) >= goal.start_date,
            func.date(Activity.created_at) <= goal.end_date).scalar() or 0
        goal.progress = round(min(100, float(consumed) / goal.target_kg * 100), 1)
    return render_template("goals.html", goals=rows)

@web.get("/achievements")
@login_required
def achievements():
    rows = Achievement.query.filter_by(user_id=current_user.id).order_by(Achievement.awarded_at.desc()).all()
    return render_template("achievements.html", items=rows)

@web.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        region = request.form.get("region", "IN-KA").strip().upper()
        if not 2 <= len(name) <= 100 or not re.fullmatch(r"[A-Z0-9-]{2,40}", region):
            flash("Please check the profile details and region code.", "error")
        else:
            current_user.name, current_user.region = name, region
            db.session.commit()
            flash("Settings saved.", "success")
            return redirect(url_for("web.settings"))
    return render_template("settings.html")

@web.get("/reports")
@login_required
def reports():
    return render_template("reports.html", stats=totals(current_user.id, 30))

@web.get("/reports/pdf")
@login_required
def report_pdf():
    stats = totals(current_user.id, 30)
    buffer = BytesIO(); pdf = canvas.Canvas(buffer, pagesize=A4); pdf.setTitle("CarbonTrack footprint report")
    pdf.setFont("Helvetica-Bold", 20); pdf.drawString(48, 790, "CarbonTrack | 30-day report")
    pdf.setFont("Helvetica", 11)
    lines = [f"Account: {current_user.name}", f"Generated: {datetime.utcnow():%Y-%m-%d %H:%M} UTC",
             f"Carbon footprint: {stats['carbon']} kg CO2e", f"Energy: {stats['energy']} kWh",
             f"Activities: {stats['count']}", f"Measured records: {stats['measured']}",
             f"Estimated records: {stats['estimated']}", "",
             "Values depend on user inputs and the configured emission factor."]
    y = 750
    for line in lines:
        pdf.drawString(48, y, line); y -= 24
    pdf.showPage(); pdf.save(); buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=carbontrack-report.pdf"})

@web.get("/reports/csv")
@login_required
def report_csv():
    rows = Activity.query.filter_by(user_id=current_user.id).order_by(Activity.created_at.desc()).limit(10000).all()
    output = StringIO(); writer = csv.writer(output)
    writer.writerow(["recorded_at_utc", "category", "description", "energy_kwh", "carbon_kg_co2e", "measurement_type", "duration_seconds", "cpu_percent", "memory_mb"])
    for row in rows:
        writer.writerow([row.created_at.isoformat(), row.category, row.description, row.energy_kwh, row.carbon_kg,
                         row.measurement_type, row.duration_seconds, row.cpu_percent, row.memory_mb])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=carbontrack-activities.csv"})

@web.get("/admin")
@login_required
def admin():
    if current_user.role != "admin": abort(403)
    return render_template("admin.html", users=User.query.count(), activities=Activity.query.count(),
                           devices=Device.query.count(), factors=EmissionFactor.query.order_by(EmissionFactor.created_at.desc()).all())

@web.post("/admin/factors")
@login_required
def add_factor():
    if current_user.role != "admin": abort(403)
    try:
        region = request.form.get("region", "").strip().upper()
        name = request.form.get("name", "").strip()
        value = float(request.form.get("kg_per_kwh", ""))
        source = request.form.get("source", "").strip()[:240]
        version = request.form.get("version", "").strip()[:40]
        if not re.fullmatch(r"[A-Z0-9-]{2,40}", region) or not name or len(name) > 120 or not 0 < value < 5 or not source or not version:
            raise ValueError
        EmissionFactor.query.filter_by(region=region, active=True).update({"active": False})
        db.session.add(EmissionFactor(region=region, name=name, kg_per_kwh=value, source=source, version=version))
        db.session.commit(); flash("Emission factor updated.", "success")
    except (ValueError, TypeError):
        db.session.rollback(); flash("Invalid factor. Value must be between 0 and 5 kg CO2e/kWh.", "error")
    return redirect(url_for("web.admin"))

@web.get("/institution")
@login_required
def institution():
    if current_user.role not in ("admin", "institution"): abort(403)
    carbon = db.session.query(func.coalesce(func.sum(Activity.carbon_kg), 0)).scalar() or 0
    return render_template("institution.html", users=User.query.count(), carbon=round(float(carbon), 3),
                           activities=Activity.query.count(), devices=Device.query.filter_by(active=True).count())
