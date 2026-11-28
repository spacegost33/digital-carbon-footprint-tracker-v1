"""Defense-in-depth helpers; existing account and route authorization remains in place."""
from flask import request, jsonify, session
from werkzeug.exceptions import HTTPException
from flask_wtf.csrf import CSRFError


def safe_csv(value):
    # Avoid spreadsheet formula execution when importing user-controlled text.
    if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t','\r','\n'))):
        return "'" + value
    return value


def configure_security(app):
    @app.before_request
    def bound_login_input():
        if request.endpoint == 'web.login' and request.method == 'POST':
            if len(request.form.get('password','')) > 128 or len(request.form.get('email','')) > 180:
                return 'Invalid email or password.', 400

    @app.after_request
    def privacy_headers(response):
        if request.path.startswith('/api/') or session.get("_user_id") or request.cookies.get(app.config.get("REMEMBER_COOKIE_NAME", "remember_token")) or request.endpoint in ('web.login','web.register'):
            response.headers['Cache-Control'] = 'private, no-store'
        # Restrict framing, injected base tags, objects and cross-origin form submissions
        # without breaking the project's existing inline scripts or Chart.js CDN.
        response.headers.setdefault('Content-Security-Policy', "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        response.headers.setdefault('X-Content-Type-Options','nosniff')
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(exc):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(error='Invalid or expired CSRF token. Reload and try again.'), 400
        return 'Invalid or expired form token. Return to the page, reload and try again.', 400

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith('/api/') or request.is_json:
            messages={400:'Invalid request.',401:'Authentication required.',403:'Access denied.',404:'Not found.',413:'Request too large.',429:'Too many requests. Try again later.',500:'Unexpected server error.',503:'Service temporarily unavailable.'}
            response=exc.get_response()
            response.set_data(app.json.dumps({'error':messages.get(exc.code,'Request failed.')}))
            response.content_type='application/json'
            return response
        return exc
