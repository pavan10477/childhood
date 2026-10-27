from flask import Flask, render_template, request
import joblib
import pandas as pd
import os

app = Flask(__name__)
MODEL_PATH = "malnutrition_model.joblib"

def load_model():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    return None

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None
    model = load_model()

    if request.method == "POST":
        try:
            child = {
                "age_months": int(request.form["age_months"]),
                "sex": request.form["sex"],
                "height_cm": float(request.form["height_cm"]),
                "weight_kg": float(request.form["weight_kg"]),
                "meals_per_day": int(request.form["meals_per_day"]),
                "fruit_veg": request.form["fruit_veg"],
                "protein_food": request.form["protein_food"],
                "appetite": request.form["appetite"],
                "previous_illness": request.form["previous_illness"],
                "immunization": request.form["immunization"],
                "sanitation": request.form["sanitation"]
            }

            if not (0 <= child["age_months"] <= 60):
                raise ValueError("This demo form is designed for children aged 0–60 months.")
            if child["height_cm"] <= 0 or child["weight_kg"] <= 0:
                raise ValueError("Height and weight must be greater than zero.")
            if not (0 <= child["meals_per_day"] <= 10):
                raise ValueError("Please enter a meals-per-day value from 0 to 10.")

            if model is None:
                error = ("Model not found. Run `python train_model.py` first. "
                         "The bundled sample data is synthetic and for software demonstration only.")
            else:
                frame = pd.DataFrame([child])
                prediction = model.predict(frame)[0]
                result = {
                    "label": str(prediction),
                    "note": ("Educational demonstration only. This result is not a medical diagnosis. "
                             "A child's nutritional status should be assessed using appropriate WHO growth "
                             "standards and by a qualified health professional.")
                }
        except ValueError as exc:
            error = str(exc)
        except Exception:
            error = "Could not process these details. Check the inputs and confirm the model has been trained."

    return render_template("index.html", result=result, error=error)

if __name__ == "__main__":
    app.run(debug=True)
