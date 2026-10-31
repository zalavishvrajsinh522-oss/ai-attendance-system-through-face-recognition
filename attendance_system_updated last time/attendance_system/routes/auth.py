import bcrypt
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)


def role_home(role):
    return {
        "principal": "principal.dashboard",
        "faculty": "faculty.dashboard",
        "student": "student.dashboard",
    }.get(role, "auth.login")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(role_home(current_user.role)))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()

        if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            login_user(user)
            return redirect(url_for(role_home(user.role)))

        flash("Invalid username/email or password.", "error")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "success")
    return redirect(url_for("auth.login"))
