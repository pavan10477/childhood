# Childhood Malnutrition Risk — Flask Project Template

## Files
- `app.py` — Flask web application
- `templates/index.html` — input form and results
- `static/style.css` — styling
- `train_model.py` — preprocessing, training and evaluation
- `sample_data.csv` — synthetic demo records only

## Run locally
1. Install Python 3.10+.
2. Open a terminal in this folder.
3. Create a virtual environment (recommended).
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Train the demonstration model:
   ```bash
   python train_model.py
   ```
6. Start the web app:
   ```bash
   python app.py
   ```
7. Open `http://127.0.0.1:5000` in your browser.

## Important data and health note
`sample_data.csv` contains synthetic records and arbitrary labels to demonstrate the software workflow only. Its accuracy is not evidence of real-world performance and must not be reported as clinical accuracy. Before making a research claim, replace it with ethically sourced, de-identified data and defensible target labels. For children under five, use the appropriate WHO growth standards/indicators (for example, height-for-age, weight-for-age and weight-for-height) with correct age, sex and measurements, and seek qualified guidance. Diet and household variables alone do not establish a diagnosis.

The current target column is `nutritional_status` with demo values `Low`, `Moderate`, and `High`. These demo labels must be replaced with validated labels before real evaluation. Report held-out test metrics including precision, recall, F1-score and a confusion matrix, not accuracy alone.
