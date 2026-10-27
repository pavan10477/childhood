import csv
import json
import tempfile
import unittest
from pathlib import Path

from risk_classifier import CSV_COLUMNS, RiskClassifier, parse_features, parse_record


def row(age, label, gender="Male"):
    return {
        "Age": str(age),
        "Gender": gender,
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


class RiskClassifierTests(unittest.TestCase):
    def test_normalizes_categories_and_predicts_nearest_record(self):
        records = [
            row(2, "High"),
            row(4, "Moderate"),
            row(6, "Low"),
        ]
        classifier = RiskClassifier([parse_record(record) for record in records])
        sample = parse_features(
            {
                "Age": "2.1",
                "Height_cm": "100",
                "Weight_kg": "15",
                "Meals_Day": "3",
                "Gender": "MALE",
                "Fruits_Veg": "Medium",
                "Protein": "Medium",
                "Physical_Activity": "Normal",
                "Previous_Illness": "No",
                "Sanitation": "Good",
            }
        )

        prediction, votes, neighbor_count = classifier.predict(sample)

        self.assertEqual(prediction, "High")
        self.assertEqual(votes, 1)
        self.assertEqual(neighbor_count, 3)

    def test_training_csv_requires_exact_fields_and_all_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "training.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as data_file:
                writer = csv.DictWriter(data_file, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(
                    [row(2, "High"), row(4, "Moderate"), row(6, "Low")]
                )

            classifier = RiskClassifier.from_csv(csv_path)

        self.assertEqual(len(classifier.records), 3)

    def test_rejects_training_csv_without_each_risk_label(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "training.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as data_file:
                writer = csv.DictWriter(data_file, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows([row(2, "High"), row(4, "High")])

            with self.assertRaisesRegex(ValueError, "all three risk labels"):
                RiskClassifier.from_csv(csv_path)

    def test_model_json_round_trip(self):
        records = [
            parse_record(row(age, label))
            for age, label in ((2, "High"), (4, "Moderate"), (6, "Low"))
        ]
        classifier = RiskClassifier(records)
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "model.json"
            classifier.to_json(model_path)
            loaded = RiskClassifier.from_json(model_path)
            self.assertEqual(json.loads(model_path.read_text(encoding="utf-8"))["records"], records)

        self.assertEqual(len(loaded.records), 3)

    def test_rejects_non_positive_measurements(self):
        invalid = row(2, "High")
        invalid["Weight_kg"] = "0"
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "training.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as data_file:
                writer = csv.DictWriter(data_file, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(
                    [invalid, row(3, "Moderate"), row(4, "Low")]
                )

            with self.assertRaisesRegex(
                ValueError, "Weight_kg must be greater than zero"
            ):
                RiskClassifier.from_csv(csv_path)


if __name__ == "__main__":
    unittest.main()
