import os
import hashlib
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import app as app_module
from risk_classifier import RiskClassifier, parse_record


def training_row(age, label):
    return parse_record(
        {
            "Age": str(age),
            "Gender": "Male",
            "Height_cm": "100",
            "Weight_kg": "15",
            "Meals_Day": "3",
            "Fruits_Veg": "Medium",
            "Protein": "Medium",
            "Physical_Activity": "Normal",
            "Previous_Illness": "No",
            "Sanitation": "Good",
            "Nutritional_Risk": label,
        }
    )


def request_data(**overrides):
    today = date.today()
    birth_date = today.replace(year=today.year - 2).isoformat()
    data = {
        "csrf_token": "test-csrf",
        "birth_date": birth_date,
        "measurement_date": today.isoformat(),
        "Gender": "Male",
        "Height_cm": "82",
        "Weight_kg": "9.5",
        "Meals_Day": "3",
        "Fruits_Veg": "Low",
        "Protein": "Low",
        "Physical_Activity": "Low",
        "Previous_Illness": "Yes",
        "Sanitation": "Poor",
        "measurement_position": "height",
        "oedema": "no",
    }
    data.update(overrides)
    return data


class AppPageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database = app_module.app.config["DATABASE"]
        self.original_model_path = app_module.RISK_MODEL_PATH
        app_module.app.config.update(
            TESTING=True,
            DATABASE=os.path.join(self.temp_dir.name, "users.sqlite3"),
        )
        app_module.RISK_MODEL_PATH = os.path.join(
            self.temp_dir.name, "nutritional_risk_model.json"
        )
        app_module.init_db()
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as state:
            state["user_id"] = 1
            state["user_email"] = "test@example.com"
            state["csrf_token"] = "test-csrf"

    def tearDown(self):
        app_module.app.config["DATABASE"] = self.original_database
        app_module.RISK_MODEL_PATH = self.original_model_path
        self.temp_dir.cleanup()

    def test_classifier_uses_only_marked_example_demo_when_model_is_missing(self):
        page = self.client.get("/risk-classifier")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="Physical_Activity"', page.data)
        self.assertIn(b'Demo mode:', page.data)
        self.assertIn(b'only the 5 unverified example rows', page.data)

        response = self.client.post(
            "/risk-classifier",
            data=request_data(),
        )
        self.assertIn(b"DEMO NUTRITIONAL RISK", response.data)
        self.assertIn(b"five unverified examples", response.data)
        self.assertIn(b"<strong>HIGH RISK</strong>", response.data)

    def test_loaded_classifier_receives_form_values_and_renders_label(self):
        classifier = RiskClassifier(
            [
                training_row(2, "High"),
                training_row(4, "Moderate"),
                training_row(6, "Low"),
            ]
        )
        classifier.to_json(Path(app_module.RISK_MODEL_PATH))

        response = self.client.post(
            "/risk-classifier",
            data=request_data(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"DATASET NUTRITIONAL RISK", response.data)
        self.assertIn(b"<strong>HIGH RISK</strong>", response.data)

    def test_login_links_to_password_recovery(self):
        with self.client.session_transaction() as state:
            state.clear()
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Forgot password?", response.data)
        self.assertIn(b'href="/forgot-password"', response.data)

    def test_password_recovery_reports_when_email_is_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/forgot-password")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Email sending is disabled", response.data)
        self.assertIn(b"SMTP_USERNAME and SMTP_PASSWORD", response.data)
        self.assertIn(b"disabled", response.data)

    def test_outlook_defaults_enable_recovery_when_credentials_are_configured(self):
        with patch.dict(
            os.environ,
            {
                "SMTP_USERNAME": "support@outlook.com",
                "SMTP_PASSWORD": "test-mail-password",
            },
            clear=True,
        ):
            response = self.client.get("/forgot-password")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Send verification code", response.data)
        self.assertNotIn(b'<button type="submit" disabled>', response.data)

    def test_send_email_uses_outlook_defaults_and_authenticates(self):
        with (
            patch.dict(
                os.environ,
                {
                    "SMTP_USERNAME": "support@outlook.com",
                    "SMTP_PASSWORD": "test-mail-password",
                },
                clear=True,
            ),
            patch.object(app_module.smtplib, "SMTP") as smtp_factory,
            patch.object(app_module.ssl, "create_default_context"),
        ):
            smtp = smtp_factory.return_value.__enter__.return_value
            app_module.send_password_reset_email(
                "member@example.com", "012345"
            )

        smtp_factory.assert_called_once_with(
            "smtp-mail.outlook.com", 587, timeout=10
        )
        smtp.login.assert_called_once_with(
            "support@outlook.com", "test-mail-password"
        )
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["From"], "support@outlook.com")
        self.assertEqual(message["To"], "member@example.com")
        self.assertIn("012345", message.get_content())

    def test_password_reset_schema_adds_attempts_to_existing_database(self):
        database_path = os.path.join(self.temp_dir.name, "legacy.sqlite3")
        with app_module.closing(
            app_module.sqlite3.connect(database_path)
        ) as db:
            db.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at INTEGER NOT NULL
                )
                """
            )
            db.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                ("member@example.com", "old-hash"),
            )
            db.execute(
                """
                INSERT INTO password_reset_tokens
                    (user_id, token_hash, expires_at)
                VALUES (?, ?, ?)
                """,
                (1, "legacy-hash", 1234567890),
            )
            db.commit()

        current_database = app_module.app.config["DATABASE"]
        app_module.app.config["DATABASE"] = database_path
        try:
            app_module.init_db()
        finally:
            app_module.app.config["DATABASE"] = current_database

        with app_module.closing(
            app_module.sqlite3.connect(database_path)
        ) as db:
            token = db.execute(
                "SELECT attempts FROM password_reset_tokens"
            ).fetchone()
        self.assertEqual(token, (0,))

    def test_forgot_password_sends_email_without_revealing_account_existence(self):
        with app_module.closing(
            app_module.sqlite3.connect(app_module.app.config["DATABASE"])
        ) as db:
            db.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                ("member@example.com", "old-hash"),
            )
            db.commit()

        mail_config = {
            "SMTP_USERNAME": "support@example.com",
            "SMTP_PASSWORD": "test-mail-password",
        }
        with (
            patch.dict(os.environ, mail_config, clear=True),
            patch.object(app_module, "send_password_reset_email") as send_email,
        ):
            response = self.client.post(
                "/forgot-password",
                data={
                    "csrf_token": "test-csrf",
                    "email": "member@example.com",
                },
            )
            unknown_account_response = self.client.post(
                "/forgot-password",
                data={
                    "csrf_token": "test-csrf",
                    "email": "unknown@example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enter your verification code", response.data)
        self.assertIn(b"If an account matches that email address", response.data)
        self.assertEqual(unknown_account_response.data, response.data)
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.args[0], "member@example.com")
        code = send_email.call_args.args[1]
        self.assertRegex(code, r"^[0-9]{6}$")
        with app_module.closing(
            app_module.sqlite3.connect(app_module.app.config["DATABASE"])
        ) as db:
            stored_code = db.execute(
                "SELECT token_hash FROM password_reset_tokens"
            ).fetchone()[0]
        self.assertEqual(stored_code, app_module.password_reset_code_hash(code))

    def test_password_reset_code_updates_password_and_is_single_use(self):
        with app_module.closing(
            app_module.sqlite3.connect(app_module.app.config["DATABASE"])
        ) as db:
            db.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                ("member@example.com", "old-hash"),
            )
            db.commit()

        with (
            patch.dict(
                os.environ,
                {
                    "SMTP_USERNAME": "support@example.com",
                    "SMTP_PASSWORD": "test-mail-password",
                },
                clear=True,
            ),
            patch.object(app_module, "send_password_reset_email") as send_email,
        ):
            sent = self.client.post(
                "/forgot-password",
                data={
                    "csrf_token": "test-csrf",
                    "action": "send_code",
                    "email": "member@example.com",
                },
            )
        self.assertIn(b"Enter your verification code", sent.data)
        code = send_email.call_args.args[1]

        response = self.client.post(
            "/forgot-password",
            data={
                "csrf_token": "test-csrf",
                "action": "reset_password",
                "code": code,
                "password": "new-strong-password",
                "confirm_password": "new-strong-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

        with app_module.closing(
            app_module.sqlite3.connect(app_module.app.config["DATABASE"])
        ) as db:
            password_hash = db.execute(
                "SELECT password_hash FROM users WHERE email = ?",
                ("member@example.com",),
            ).fetchone()[0]
            remaining_codes = db.execute(
                "SELECT COUNT(*) FROM password_reset_tokens"
            ).fetchone()[0]
        self.assertTrue(
            app_module.check_password_hash(password_hash, "new-strong-password")
        )
        self.assertEqual(remaining_codes, 0)

    def test_password_reset_code_is_limited_to_five_attempts(self):
        with app_module.closing(
            app_module.sqlite3.connect(app_module.app.config["DATABASE"])
        ) as db:
            db.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                ("member@example.com", "old-hash"),
            )
            db.commit()

        with (
            patch.dict(
                os.environ,
                {
                    "SMTP_USERNAME": "support@example.com",
                    "SMTP_PASSWORD": "test-mail-password",
                },
                clear=True,
            ),
            patch.object(app_module, "send_password_reset_email"),
            patch.object(app_module.secrets, "randbelow", return_value=12345),
        ):
            self.client.post(
                "/forgot-password",
                data={
                    "csrf_token": "test-csrf",
                    "action": "send_code",
                    "email": "member@example.com",
                },
            )

        for _ in range(5):
            response = self.client.post(
                "/forgot-password",
                data={
                    "csrf_token": "test-csrf",
                    "action": "reset_password",
                    "code": "000000",
                    "password": "new-strong-password",
                    "confirm_password": "new-strong-password",
                },
            )
        self.assertIn(b"invalid or has expired", response.data)
        with app_module.closing(
            app_module.sqlite3.connect(app_module.app.config["DATABASE"])
        ) as db:
            remaining_codes = db.execute(
                "SELECT COUNT(*) FROM password_reset_tokens"
            ).fetchone()[0]
        self.assertEqual(remaining_codes, 0)

    def test_password_reset_token_updates_password_and_is_single_use(self):
        with app_module.closing(
            app_module.sqlite3.connect(app_module.app.config["DATABASE"])
        ) as db:
            db.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                ("member@example.com", "old-hash"),
            )
            reset_token = "single-use-reset-token"
            db.execute(
                """
                INSERT INTO password_reset_tokens
                    (user_id, token_hash, expires_at)
                VALUES (?, ?, ?)
                """,
                (
                    1,
                    hashlib.sha256(reset_token.encode("utf-8")).hexdigest(),
                    int(datetime.now(timezone.utc).timestamp()) + 1800,
                ),
            )
            db.commit()

        response = self.client.post(
            f"/reset-password/{reset_token}",
            data={
                "csrf_token": "test-csrf",
                "password": "new-strong-password",
                "confirm_password": "new-strong-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

        reused = self.client.post(
            f"/reset-password/{reset_token}",
            data={
                "csrf_token": "test-csrf",
                "password": "another-password",
                "confirm_password": "another-password",
            },
        )
        self.assertEqual(reused.status_code, 200)
        self.assertIn(b"invalid or has expired", reused.data)

        with self.client.session_transaction() as state:
            state.clear()
            state["csrf_token"] = "test-csrf"
        login_response = self.client.post(
            "/login",
            data={
                "csrf_token": "test-csrf",
                "email": "member@example.com",
                "password": "new-strong-password",
            },
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.headers["Location"], "/who-screening")

    def test_shows_screenshot_style_result_with_who_indicators(self):
        response = self.client.post(
            "/risk-classifier",
            data=request_data(
                birth_date=date.today().replace(year=date.today().year - 4).isoformat(),
                Gender="Male",
                Height_cm="88",
                Weight_kg="10",
                Meals_Day="2",
                Fruits_Veg="Low",
                Protein="Low",
                Physical_Activity="Low",
                Previous_Illness="Yes",
                Sanitation="Poor",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Child details", response.data)
        self.assertIn(b"DEMO NUTRITIONAL RISK", response.data)
        self.assertIn(b"WHO growth indicators", response.data)
        self.assertIn(b"Stunting (height-for-age)", response.data)
        self.assertIn(b"Wasting (weight-for-height)", response.data)
        self.assertIn(b"Underweight (weight-for-age)", response.data)
        self.assertIn(b"Low fruit and vegetable intake selected", response.data)
        self.assertIn(b"Previous illness reported", response.data)
        self.assertIn(b"not be used for a child", response.data)

    def test_who_screening_remains_available(self):
        response = self.client.get("/who-screening")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"WHO Child Growth Screening", response.data)
        self.assertIn(b'name="age_years"', response.data)
        self.assertNotIn(b'name="birth_date"', response.data)
        self.assertNotIn(b'name="measurement_position"', response.data)
        self.assertNotIn(b'name="oedema"', response.data)

    def test_main_page_uses_four_fields_and_calculates_who_results(self):
        page = self.client.get("/demo")
        self.assertEqual(page.status_code, 200)
        for field in (b"age_years", b"sex", b"length_height_cm", b"weight_kg"):
            self.assertIn(b'name="' + field + b'"', page.data)
        for field in (b"birth_date", b"measurement_position", b"oedema"):
            self.assertNotIn(b'name="' + field + b'"', page.data)

        response = self.client.post(
            "/demo",
            data={
                "csrf_token": "test-csrf",
                "age_years": "4.5",
                "sex": "Female",
                "weight_kg": "16",
                "length_height_cm": "102",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<h2>Child Nutrition Report</h2>", response.data)
        self.assertIn(b"1. Stunting", response.data)
        self.assertIn(b"3. Underweight", response.data)
        self.assertIn(b"2. Wasting / overweight", response.data)
        self.assertNotIn(b"Z-score", response.data)
        self.assertNotIn(b" SD", response.data)
        self.assertNotIn(b"months old", response.data)
        self.assertIn(b"Sample child: Age 4.5 years", response.data)
        self.assertIn(b"LOW NUTRITIONAL CONCERN", response.data)
        self.assertIn("class=\"concern-icon\" aria-hidden=\"true\">✓".encode(), response.data)
        self.assertNotIn(b"Meaning:", response.data)
        self.assertEqual(response.data.count(b"Precaution:"), 3)
        self.assertIn(b"Disclaimer:", response.data)

    def test_who_screening_accepts_age_and_displays_separate_results(self):
        response = self.client.post(
            "/who-screening",
            data={
                "csrf_token": "test-csrf",
                "age_years": "4.5",
                "sex": "Female",
                "weight_kg": "16",
                "length_height_cm": "102",
                "measurement_position": "height",
                "oedema": "no",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<h2>Child Nutrition Report</h2>", response.data)
        self.assertIn(b"1. Stunting", response.data)
        self.assertIn(b"3. Underweight", response.data)
        self.assertIn(b"2. Wasting / overweight", response.data)
        self.assertIn(b"Low Concern", response.data)
        self.assertNotIn(b"Z-score", response.data)
        self.assertNotIn(b" SD", response.data)
        self.assertNotIn(b"-0.92", response.data)
        self.assertNotIn(b"Meaning:", response.data)
        self.assertEqual(response.data.count(b"Precaution:"), 3)
        self.assertIn(b"routine height monitoring", response.data)
        self.assertIn(b"routine weight monitoring", response.data)

    def test_report_flags_sample_measurements_as_concern_without_scores(self):
        response = self.client.post(
            "/demo",
            data={
                "csrf_token": "test-csrf",
                "age_years": "4",
                "sex": "Male",
                "length_height_cm": "88",
                "weight_kg": "10",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"HIGH NUTRITIONAL CONCERN", response.data)
        self.assertEqual(response.data.count(b"High Concern"), 3)
        self.assertNotIn(b"Meaning:", response.data)
        self.assertNotIn(b"Meaning:", response.data)
        self.assertIn(
            b"Give a balanced diet with eggs, dal, milk or curd, vegetables",
            response.data,
        )
        self.assertIn(b"Offer regular, age-appropriate meals with energy-rich", response.data)
        self.assertIn(b"suitable nut pastes where safe", response.data)
        self.assertIn(b"Provide nutritious food", response.data)
        self.assertIn(b"feed the child regularly", response.data)
        self.assertIn(b"maintain good hygiene", response.data)
        self.assertIn(b"monitor the child&#39;s growth", response.data)
        self.assertNotIn(b"Z-score", response.data)

    def test_overweight_has_its_own_precaution(self):
        response = self.client.post(
            "/demo",
            data={
                "csrf_token": "test-csrf",
                "age_years": "4.5",
                "sex": "Female",
                "length_height_cm": "102",
                "weight_kg": "30",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<strong>High Concern</strong>", response.data)
        self.assertIn(b"avoid restrictive diets", response.data)


if __name__ == "__main__":
    unittest.main()
