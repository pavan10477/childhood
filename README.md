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
The sign-in page includes a one-time password-reset link flow. To enable email delivery, configure these environment variables before starting the app:

- `SMTP_HOST`: SMTP server hostname.
- `SMTP_PORT`: SMTP submission port (defaults to `587`; STARTTLS is used).
- `SMTP_FROM`: sender address.
- `SMTP_USERNAME` and `SMTP_PASSWORD`: both required when the SMTP server requires authentication.
- `PUBLIC_BASE_URL`: public application origin, for example `https://your-domain.example`.

Keep SMTP credentials out of source control. Reset tokens are stored only as hashes, expire after 30 minutes, and are invalidated after use. If mail settings are missing, the recovery page explains that email recovery is unavailable and directs users to the site administrator.
