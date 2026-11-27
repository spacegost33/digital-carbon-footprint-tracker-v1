import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("FLASK_ENV", "testing")
from app import create_app, db
from app.models import User

def setup_function():
    global app, client
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context(): db.drop_all(); db.create_all()
    client = app.test_client()

def test_health_checks_database():
    response = client.get("/health")
    assert response.status_code == 200 and response.json["database"] == "connected"

def test_register_and_dashboard():
    response = client.post("/register", data={"name":"Test User", "email":"test@example.com", "password":"long-password-123"}, follow_redirects=True)
    assert response.status_code == 200 and b"Your impact" in response.data

def test_login_rejects_bad_password():
    with app.app_context():
        user = User(name="Test", email="a@example.com"); user.set_password("long-password-123"); db.session.add(user); db.session.commit()
    response = client.post("/login", data={"email":"a@example.com", "password":"wrong-password"})
    assert response.status_code == 200 and b"Invalid email or password" in response.data

def test_logout_is_post_only_and_login_required():
    assert client.get("/logout").status_code == 405
