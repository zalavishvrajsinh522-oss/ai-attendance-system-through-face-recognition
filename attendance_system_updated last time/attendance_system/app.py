import os
from datetime import datetime
from flask import Flask, redirect, url_for
from flask_login import current_user

from config import Config
from extensions import db, login_manager
from models import User


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    from routes.auth import auth_bp
    from routes.principal import principal_bp
    from routes.faculty import faculty_bp
    from routes.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(principal_bp, url_prefix="/principal")
    app.register_blueprint(faculty_bp, url_prefix="/faculty")
    app.register_blueprint(student_bp, url_prefix="/student")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(role_home(current_user.role))
        return redirect(url_for("auth.login"))

    @app.context_processor
    def inject_now():
        return {"current_year": datetime.utcnow().year}

    with app.app_context():
        db.create_all()
        from utils.migrations import ensure_schema_upgrades
        ensure_schema_upgrades(db)
        _seed_default_principal()

    return app


def role_home(role):
    return {
        "principal": "principal.dashboard",
        "faculty": "faculty.dashboard",
        "student": "student.dashboard",
    }.get(role, "auth.login")


def _seed_default_principal():
    """Create a default Principal login on first run so the app is usable immediately."""
    import bcrypt
    if User.query.filter_by(role="principal").first():
        return
    pw_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
    admin = User(username="admin", email="admin@example.com",
                 password_hash=pw_hash, role="principal")
    db.session.add(admin)
    db.session.commit()
    print("=" * 60)
    print("Created default Principal login -> username: admin | password: admin123")
    print("Please change this password after first login.")
    print("=" * 60)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
