# Childhood Malnutrition Project

## Run locally
1. Use Python 3.10 or later and open a terminal in this folder.
2. Create a virtual environment if desired.
3. Install the web dependency:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   python app.py
   ```
5. Open `http://127.0.0.1:5000`, create an account and sign in.

## Nutritional risk classifier
The separate **Dataset Nutritional Risk Classifier** page uses the fields and target from the supplied table:

`Age, Gender, Height_cm, Weight_kg, Meals_Day, Fruits_Veg, Protein, Physical_Activity, Previous_Illness, Sanitation, Nutritional_Risk`

The five supplied rows are saved as `data/nutritional_risk_examples_unverified.csv`. If no full-dataset model is installed, the app can show a nearest-neighbor **software demo output** using those five example rows. This is unverified, unreliable, has no established health meaning, and must not be used for a child's care.

When you have the verified full dataset, save a copy as `data/nutritional_risk_data.csv` with the exact headers above and run:
```bash
python train_model.py
```
The app will then use `nutritional_risk_model.json` instead of the five-row demo. Both the dataset and generated model are excluded from Git by `.gitignore`. The CSV structure is in `data/nutritional_risk_data.csv.template`.

Training a classifier does not establish that its labels or predictions are medically valid. Confirm how `Nutritional_Risk` was determined, use authorized and de-identified data, and evaluate the model on a separate representative dataset with appropriate clinical guidance before interpreting predictions. The built-in nearest-neighbor method is a simple project baseline, not a clinical decision tool.

## WHO growth screening
The main assessment accepts age in years, sex, height/length and weight. It converts age to months internally and calculates HAZ (height-for-age), WAZ (weight-for-age) and WHZ (weight-for-height) using LMS tables from the [WHO Anthro R package](https://github.com/WorldHealthOrganization/anthro/tree/b776d8a12b1c97369c748b561159fd2ec4f4db58/data-raw/growthstandards), pinned to revision `b776d8a12b1c97369c748b561159fd2ec4f4db58`. The package's GPL-3 license is included in `data/who_growth_standards/LICENSE.md`.

The four-field quick screen assumes no bilateral pitting oedema and the age-appropriate standard position (lying length below 2 years; standing height from 2 years). These assumptions can affect weight-based z-scores. WHO indicators are for screening, not diagnosis; results should be interpreted by a qualified health professional. See [WHO indicator definitions](https://www.who.int/data/nutrition/nlis/info/malnutrition) and [WHO Child Growth Standards tools](https://www.who.int/tools/child-growth-standards/software).

Accounts are stored in `instance/users.sqlite3`; passwords are stored as hashes. Set a stable `SECRET_KEY` environment variable before deployment.

### Password recovery
The sign-in page includes a six-digit email verification code flow. Codes expire after 10 minutes, can be tried at most five times, and are stored only as keyed hashes. Email sending requires `SMTP_USERNAME` and `SMTP_PASSWORD`:

- `SMTP_USERNAME`: full mailbox email address used to authenticate.
- `SMTP_PASSWORD`: mailbox or provider-issued app password.
- `SMTP_HOST`: SMTP server hostname (defaults to `smtp-mail.outlook.com`).
- `SMTP_PORT`: SMTP submission port (defaults to `587`; STARTTLS is used).
- `SMTP_FROM`: sender address (defaults to `SMTP_USERNAME`).

Keep SMTP credentials out of source control and set a stable `SECRET_KEY` in production. If mail settings are missing, the recovery page explains that email recovery is unavailable and directs users to the site administrator. Previously issued reset links remain valid until they expire.

#### Render with a personal Outlook mailbox
In the Render dashboard, open the web service, select **Environment**, and add:

- `SMTP_USERNAME`: the same full Outlook email address.
- `SMTP_PASSWORD`: the mailbox password, or an app password if two-step verification is enabled and Outlook provides app passwords.
- `SECRET_KEY`: a long, random value that remains unchanged between deploys.

The app defaults to Outlook's `smtp-mail.outlook.com` on port `587`, and uses `SMTP_USERNAME` as the sender, so `SMTP_HOST`, `SMTP_PORT`, and `SMTP_FROM` do not need to be added for this setup. Save the environment settings and redeploy/restart the service. Keep the password and secret only in Render's environment settings, not in GitHub or source files. Outlook account security settings may block SMTP AUTH; if SMTP login is rejected, enable authenticated SMTP for the mailbox if available or use a mail provider that supports SMTP credentials.
