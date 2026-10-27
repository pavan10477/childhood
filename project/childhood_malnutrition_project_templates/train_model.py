"""
Train a demonstration classifier.

IMPORTANT:
- sample_data.csv contains SYNTHETIC example data and arbitrary demo labels.
- Do not use its scores or predictions for health decisions or academic claims.
- For a real project, replace it with ethically sourced, de-identified data and labels
  defined using appropriate WHO growth indicators / qualified clinical guidance.
"""
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

DATA_PATH = "sample_data.csv"
MODEL_PATH = "malnutrition_model.joblib"

numeric = ["age_months", "height_cm", "weight_kg", "meals_per_day"]
categorical = [
    "sex", "fruit_veg", "protein_food", "appetite",
    "previous_illness", "immunization", "sanitation"
]
target = "nutritional_status"

df = pd.read_csv(DATA_PATH)
X = df[numeric + categorical]
y = df[target]

preprocess = ColumnTransformer([
    ("num", Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler())
    ]), numeric),
    ("cat", Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore"))
    ]), categorical)
])

model = Pipeline([
    ("preprocess", preprocess),
    ("classifier", RandomForestClassifier(n_estimators=150, random_state=42,
                                          class_weight="balanced"))
])

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
model.fit(X_train, y_train)
pred = model.predict(X_test)

print("DEMO ONLY — these metrics are not medically meaningful because the dataset is synthetic.")
print(f"Hold-out accuracy: {accuracy_score(y_test, pred):.3f}")
print("\nClassification report:\n", classification_report(y_test, pred, zero_division=0))
print("Confusion matrix:\n", confusion_matrix(y_test, pred))

# Train on all available demo rows for the web app after evaluation.
model.fit(X, y)
joblib.dump(model, MODEL_PATH)
print(f"\nSaved demo model to {MODEL_PATH}")
