from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
import hashlib
import hmac
import os
import secrets
import smtplib
import ssl
import sqlite3
from pathlib import Path
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from risk_classifier import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    RiskClassifier,
    parse_features,
)
from who_screening import (
    LAST_REFERENCE_AGE_DAYS,
    calculate_screening,
    calculate_screening_by_age,
)

app = Flask(__name__, template_folder=os.path.join("instance", "templates"))
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["DATABASE"] = os.path.join(app.instance_path, "users.sqlite3")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RISK_MODEL_PATH = os.path.join(BASE_DIR, "nutritional_risk_model.json")
RISK_EXAMPLES_PATH = os.path.join(
    BASE_DIR, "data", "nutritional_risk_examples_unverified.csv"
)

def init_db():
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    with closing(sqlite3.connect(app.config["DATABASE"])) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at INTEGER NOT NULL
            )
            """
        )
        db.commit()


def csrf_token():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def valid_csrf_token():
    submitted = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    return bool(expected and submitted and hmac.compare_digest(submitted, expected))


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@app.after_request
def set_session_cookie_options(response):
    response.headers["Cache-Control"] = "no-store"
    return response


init_db()


def load_risk_classifier():
    if os.path.isfile(RISK_MODEL_PATH):
        return RiskClassifier.from_json(Path(RISK_MODEL_PATH).resolve()), False
    return RiskClassifier.from_csv(Path(RISK_EXAMPLES_PATH)), True


def password_reset_email_configured():
    return bool(
        os.environ.get("SMTP_HOST", "").strip()
        and os.environ.get("SMTP_FROM", "").strip()
        and os.environ.get("PUBLIC_BASE_URL", "").strip()
    )


def send_password_reset_email(email, token):
    host = os.environ["SMTP_HOST"].strip()
    sender = os.environ["SMTP_FROM"].strip()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    base_url = os.environ["PUBLIC_BASE_URL"].strip().rstrip("/")
    port = int(os.environ.get("SMTP_PORT", "587"))
    if bool(username) != bool(password):
        raise ValueError("Configure both SMTP_USERNAME and SMTP_PASSWORD, or neither.")

    reset_url = f"{base_url}{url_for('reset_password', token=token)}"
    message = EmailMessage()
    message["Subject"] = "Reset your GrowWell password"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "We received a request to reset your GrowWell password.\n\n"
        f"Use this one-time link within 30 minutes:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )

    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        if not valid_csrf_token():
            flash("Your form expired. Please try again.", "error")
            return render_template("login.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with closing(sqlite3.connect(app.config["DATABASE"])) as db:
            db.row_factory = sqlite3.Row
            user = db.execute(
                "SELECT id, email, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        flash("Signed in successfully.", "success")
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    error = None
    if request.method == "POST":
        if not valid_csrf_token():
            error = "Your form expired. Refresh the page and try again."
        elif not password_reset_email_configured():
            error = (
                "Password reset email is not configured. Please contact the "
                "site administrator."
            )
        else:
            email = request.form.get("email", "").strip().lower()
            with closing(sqlite3.connect(app.config["DATABASE"])) as db:
                db.row_factory = sqlite3.Row
                user = db.execute(
                    "SELECT id, email FROM users WHERE email = ?", (email,)
                ).fetchone()

            if user is not None:
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                expires_at = int(
                    (
                        datetime.now(timezone.utc)
                        + timedelta(minutes=30)
                    ).timestamp()
                )
                with closing(sqlite3.connect(app.config["DATABASE"])) as db:
                    db.execute(
                        "DELETE FROM password_reset_tokens WHERE user_id = ?",
                        (user["id"],),
                    )
                    db.execute(
                        """
                        INSERT INTO password_reset_tokens
                            (user_id, token_hash, expires_at)
                        VALUES (?, ?, ?)
                        """,
                        (user["id"], token_hash, expires_at),
                    )
                    db.commit()

                try:
                    send_password_reset_email(user["email"], token)
                except (OSError, smtplib.SMTPException, ValueError, KeyError):
                    app.logger.exception("Password reset email could not be sent")
                    with closing(sqlite3.connect(app.config["DATABASE"])) as db:
                        db.execute(
                            "DELETE FROM password_reset_tokens WHERE token_hash = ?",
                            (token_hash,),
                        )
                        db.commit()

            return render_template(
                "forgot_password.html",
                reset_email_configured=True,
                submitted=True,
                error=None,
            )

    return render_template(
        "forgot_password.html",
        reset_email_configured=password_reset_email_configured(),
        submitted=False,
        error=error,
    )


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    error = None
    if request.method == "POST":
        if not valid_csrf_token():
            error = "Your form expired. Refresh the page and try again."
        else:
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            if len(password) < 8:
                error = "Password must be at least 8 characters long."
            elif password != confirm_password:
                error = "Passwords do not match."
            else:
                token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                now = int(datetime.now(timezone.utc).timestamp())
                with closing(sqlite3.connect(app.config["DATABASE"])) as db:
                    db.execute("BEGIN IMMEDIATE")
                    reset_token = db.execute(
                        """
                        SELECT user_id FROM password_reset_tokens
                        WHERE token_hash = ? AND expires_at > ?
                        """,
                        (token_hash, now),
                    ).fetchone()
                    if reset_token is None:
                        db.rollback()
                        error = "This reset link is invalid or has expired."
                    else:
                        db.execute(
                            "UPDATE users SET password_hash = ? WHERE id = ?",
                            (
                                generate_password_hash(password),
                                reset_token[0],
                            ),
                        )
                        db.execute(
                            "DELETE FROM password_reset_tokens WHERE user_id = ?",
                            (reset_token[0],),
                        )
                        db.commit()

                if error is None:
                    flash("Password updated. Please sign in.", "success")
                    return redirect(url_for("login"))

    return render_template("reset_password.html", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        if not valid_csrf_token():
            flash("Your form expired. Please try again.", "error")
            return render_template("signup.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            flash("Enter a valid email address.", "error")
            return render_template("signup.html")
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("signup.html")
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        try:
            with closing(sqlite3.connect(app.config["DATABASE"])) as db:
                db.execute(
                    "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (email, generate_password_hash(password)),
                )
                db.commit()
        except sqlite3.IntegrityError:
            flash("An account with that email already exists. Please sign in.", "error")
            return render_template("signup.html")

        flash("Account created. Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    if not valid_csrf_token():
        flash("Your form expired. Please try again.", "error")
        return redirect(url_for("index"))
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/risk-classifier", methods=["GET", "POST"])
@login_required
def risk_classifier():
    result = None
    error = None
    classifier, demo_mode = load_risk_classifier()

    if request.method == "POST":
        if not valid_csrf_token():
            error = "Your form expired. Refresh the page and try again."
        else:
            try:
                birth_date = date.fromisoformat(request.form.get("birth_date", ""))
                measurement_date = date.fromisoformat(
                    request.form.get("measurement_date", "")
                )
                age_days = (measurement_date - birth_date).days
                if age_days < 0:
                    raise ValueError("Measurement date cannot be earlier than the birth date.")
                if measurement_date > date.today():
                    raise ValueError("Measurement date cannot be in the future.")

                row = {
                    field: request.form.get(field, "")
                    for field in CATEGORICAL_FEATURES
                }
                row.update(
                    {
                        field: request.form.get(field, "")
                        for field in NUMERIC_FEATURES
                        if field != "Age"
                    }
                )
                row["Age"] = str(age_days / 365.25)
                sample = parse_features(row)
                prediction, votes, neighbor_count = classifier.predict(sample)
                screening = None
                screening_note = None
                if age_days <= LAST_REFERENCE_AGE_DAYS:
                    screening = calculate_screening(
                        birth_date=birth_date,
                        measurement_date=measurement_date,
                        sex=request.form.get("Gender", ""),
                        weight_kg=request.form.get("Weight_kg", ""),
                        length_height_cm=request.form.get("Height_cm", ""),
                        measurement_position=request.form.get(
                            "measurement_position", ""
                        ),
                        oedema=request.form.get("oedema", ""),
                    )
                else:
                    screening_note = (
                        "WHO growth indicators are available only through the "
                        f"last reference age ({LAST_REFERENCE_AGE_DAYS} days, "
                        "approximately 5 years)."
                    )

                reported_factors = []
                if request.form.get("Fruits_Veg", "").casefold() == "low":
                    reported_factors.append("Low fruit and vegetable intake selected")
                if request.form.get("Protein", "").casefold() == "low":
                    reported_factors.append("Low protein intake selected")
                if request.form.get("Physical_Activity", "").casefold() == "low":
                    reported_factors.append("Low physical activity selected")
                if request.form.get("Previous_Illness", "").casefold() == "yes":
                    reported_factors.append("Previous illness reported")
                if request.form.get("Sanitation", "").casefold() == "poor":
                    reported_factors.append("Poor sanitation selected")

                result = {
                    "label": prediction,
                    "votes": votes,
                    "neighbor_count": neighbor_count,
                    "demo_mode": demo_mode,
                    "age_years": f"{age_days / 365.25:.1f}",
                    "gender": request.form.get("Gender", ""),
                    "height_cm": request.form.get("Height_cm", ""),
                    "weight_kg": request.form.get("Weight_kg", ""),
                    "meals_day": request.form.get("Meals_Day", ""),
                    "fruits_veg": request.form.get("Fruits_Veg", ""),
                    "protein": request.form.get("Protein", ""),
                    "physical_activity": request.form.get("Physical_Activity", ""),
                    "previous_illness": request.form.get("Previous_Illness", ""),
                    "sanitation": request.form.get("Sanitation", ""),
                    "screening": screening,
                    "screening_note": screening_note,
                    "reported_factors": reported_factors,
                }
            except ValueError as exc:
                error = str(exc)

    return render_template(
        "index.html",
        result=result,
        error=error,
        demo_mode=demo_mode,
        today=date.today().isoformat(),
    )


@app.route("/demo", methods=["GET", "POST"])
@app.route("/who-screening", methods=["GET", "POST"])
@login_required
def index():
    result = None
    error = None

    if request.method == "POST":
        if not valid_csrf_token():
            error = "Your form expired. Refresh the page and try again."
        else:
            try:
                result = calculate_screening_by_age(
                    age_years=request.form.get("age_years", ""),
                    sex=request.form.get("sex", ""),
                    weight_kg=request.form.get("weight_kg", ""),
                    length_height_cm=request.form.get("length_height_cm", ""),
                    oedema="no",
                )
            except ValueError as exc:
                error = str(exc)

    return render_template(
        "who_screening.html",
        result=result,
        error=error,
    )

if __name__ == "__main__":
    app.run(debug=True)
