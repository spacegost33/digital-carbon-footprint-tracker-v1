"""Authenticated benchmarking UI and per-user history."""
import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user

from . import db, limiter
from .services import active_factor
from .benchmark_logic import validate_input

benchmark = Blueprint('benchmark', __name__)
_worker_lock = threading.Lock()


class BenchmarkRun(db.Model):
    __tablename__ = 'benchmark_run'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    result_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


@benchmark.get('/benchmark')
@login_required
def overview():
    history = BenchmarkRun.query.filter_by(user_id=current_user.id).order_by(
        BenchmarkRun.id.desc()).limit(30).all()
    entries = [(row, json.loads(row.result_json)) for row in history]
    selected = request.args.get('run', type=int)
    result = entries[0][1] if entries else None
    if selected is not None:
        row = BenchmarkRun.query.filter_by(id=selected, user_id=current_user.id).first_or_404()
        result = json.loads(row.result_json)
    return render_template('benchmark.html', result=result, history=entries,
                           factor=active_factor(current_user.region))


@benchmark.post('/benchmark/run')
@login_required
@limiter.limit('6 per minute; 30 per hour')
def run():
    try:
        kind = request.form.get('kind', '')
        size = int(request.form.get('size', ''))
        watts, factor = validate_input(kind, size, request.form.get('watts', ''),
                                       active_factor(current_user.region))
    except (ValueError, TypeError, OverflowError):
        flash('Choose a supported benchmark, 100–2000 items, and 0–1000 W (greater than zero).', 'error')
        return redirect(url_for('benchmark.overview'))
    if not _worker_lock.acquire(blocking=False):
        flash('A benchmark is already running in this worker. Try again shortly.', 'info')
        return redirect(url_for('benchmark.overview'))
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).with_name('benchmark_logic.py')),
             kind, str(size), str(watts), str(factor)],
            capture_output=True, text=True, timeout=12, check=True, shell=False)
        result = json.loads(completed.stdout)
    except (subprocess.SubprocessError, OSError, ValueError):
        flash('Benchmark could not complete. Try a smaller workload.', 'error')
        return redirect(url_for('benchmark.overview'))
    finally:
        _worker_lock.release()
    row = BenchmarkRun(user_id=current_user.id, result_json=json.dumps(result, allow_nan=False))
    db.session.add(row)
    db.session.commit()
    flash('Benchmark completed. Results saved separately from personal emissions.', 'success')
    return redirect(url_for('benchmark.overview', run=row.id))
