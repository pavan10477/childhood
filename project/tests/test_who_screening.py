import unittest
from datetime import date, timedelta

from who_screening import (
    LAST_REFERENCE_AGE_DAYS,
    _compute_zscore,
    _height_status,
    _weight_for_length_height_status,
    _weight_status,
    calculate_screening,
    calculate_screening_by_age,
    load_growth_standards,
)


class WhoScreeningTests(unittest.TestCase):
    def test_matches_who_anthro_length_for_age_example(self):
        result = calculate_screening(
            birth_date=date(2022, 1, 1),
            measurement_date=date(2022, 1, 1) + timedelta(days=44),
            sex="Male",
            weight_kg="3.5",
            length_height_cm="50",
            measurement_position="length",
            oedema="no",
        )

        height_for_age = result["indicators"][0]
        self.assertEqual(height_for_age["name"], "Length/height-for-age")
        self.assertEqual(height_for_age["z_score"], "-3.29")

    def test_matches_who_anthro_weight_for_age_example(self):
        result = calculate_screening(
            birth_date=date(2022, 1, 1),
            measurement_date=date(2022, 1, 1) + timedelta(days=1522),
            sex="Female",
            weight_kg="17",
            length_height_cm="100",
            measurement_position="height",
            oedema="no",
        )

        weight_for_age = result["indicators"][1]
        self.assertEqual(weight_for_age["name"], "Weight-for-age")
        self.assertEqual(weight_for_age["z_score"], "0.24")
        self.assertEqual(weight_for_age["status"], "Underweight: No")

    def test_uses_shared_boys_weight_for_age_reference_row(self):
        standards = load_growth_standards()
        self.assertEqual(
            standards.weight_for_age[(1, 1461)],
            (-0.1131, 16.3489, 0.12759),
        )

        result = calculate_screening_by_age(
            age_years="4",
            sex="Male",
            weight_kg="16",
            length_height_cm="100",
            oedema="no",
        )
        weight_for_age = next(
            item
            for item in result["indicators"]
            if item["name"] == "Weight-for-age"
        )
        self.assertEqual(weight_for_age["status"], "Underweight: No")
        self.assertEqual(weight_for_age["concern_level"], "Low Concern")

    def test_reports_underweight_when_weight_for_age_is_below_minus_two_sd(self):
        result = calculate_screening(
            birth_date=date(2024, 1, 1),
            measurement_date=date(2024, 1, 1) + timedelta(days=365),
            sex="Male",
            weight_kg="5",
            length_height_cm="70",
            measurement_position="length",
            oedema="no",
        )

        weight_for_age = result["indicators"][1]
        self.assertTrue(weight_for_age["z_score"].startswith("-"))
        self.assertIn("Underweight: Yes", weight_for_age["status"])
        self.assertIn("energy-rich nutritious foods", weight_for_age["precaution"])
        self.assertIn("suitable nut pastes where safe", weight_for_age["precaution"])

    def test_applies_who_thresholds_before_rounding_hidden_z_scores(self):
        just_below_minus_two = _compute_zscore(79.99, (1.0, 100.0, 0.1), False)
        just_above_minus_two = _compute_zscore(80.01, (1.0, 100.0, 0.1), False)
        just_above_plus_two = _compute_zscore(120.01, (1.0, 100.0, 0.1), False)

        self.assertLess(just_below_minus_two, -2)
        self.assertEqual(_height_status(just_below_minus_two), "Stunting: Yes")
        self.assertEqual(_weight_status(just_below_minus_two), "Underweight: Yes")
        self.assertEqual(
            _weight_for_length_height_status(just_below_minus_two), "Wasting: Yes"
        )
        self.assertGreater(just_above_minus_two, -2)
        self.assertEqual(_height_status(just_above_minus_two), "Stunting: No")
        self.assertGreater(just_above_plus_two, 2)
        self.assertEqual(
            _weight_for_length_height_status(just_above_plus_two), "Overweight: Yes"
        )

    def test_uses_who_standing_height_adjustment_before_two_years(self):
        result = calculate_screening(
            birth_date=date(2024, 1, 1),
            measurement_date=date(2024, 1, 1) + timedelta(days=730),
            sex="Male",
            weight_kg="12",
            length_height_cm="100",
            measurement_position="height",
            oedema="no",
        )

        self.assertEqual(result["position_adjustment_cm"], "+0.7")
        self.assertEqual(result["standardized_measurement_cm"], "100.7")

    def test_omits_weight_indicators_when_oedema_is_not_ruled_out(self):
        result = calculate_screening(
            birth_date=date(2024, 1, 1),
            measurement_date=date(2024, 1, 1) + timedelta(days=100),
            sex="Female",
            weight_kg="5",
            length_height_cm="60",
            measurement_position="length",
            oedema="unsure",
        )

        self.assertEqual(result["indicators"][0]["name"], "Length/height-for-age")
        self.assertTrue(
            all(
                item["z_score"] == "Not calculated"
                for item in result["indicators"][1:]
            )
        )
        self.assertTrue(
            all("result is unavailable" in item["precaution"]
                for item in result["indicators"][1:])
        )

    def test_reports_measurement_outside_weight_for_height_reference_range(self):
        result = calculate_screening(
            birth_date=date(2024, 1, 1),
            measurement_date=date(2024, 1, 1) + timedelta(days=100),
            sex="Female",
            weight_kg="5",
            length_height_cm="44",
            measurement_position="length",
            oedema="no",
        )

        weight_for_length_height = result["indicators"][2]
        self.assertEqual(weight_for_length_height["z_score"], "Not calculated")
        self.assertIn("45–110 cm", weight_for_length_height["status"])

    def test_rejects_age_outside_under_five_reference(self):
        with self.assertRaisesRegex(ValueError, "approximately 5 years"):
            calculate_screening(
                birth_date=date(2020, 1, 1),
                measurement_date=date(2020, 1, 1)
                + timedelta(days=LAST_REFERENCE_AGE_DAYS + 1),
                sex="Male",
                weight_kg="18",
                length_height_cm="105",
                measurement_position="height",
                oedema="no",
            )

    def test_calculates_screening_at_last_available_reference_age(self):
        result = calculate_screening(
            birth_date=date(2020, 1, 1),
            measurement_date=date(2020, 1, 1)
            + timedelta(days=LAST_REFERENCE_AGE_DAYS),
            sex="Female",
            weight_kg="16",
            length_height_cm="102",
            measurement_position="height",
            oedema="no",
        )

        self.assertEqual(result["age_days"], LAST_REFERENCE_AGE_DAYS)
        self.assertEqual(len(result["indicators"]), 3)

    def test_converts_age_years_to_months_and_calculates_all_indicators(self):
        result = calculate_screening_by_age(
            age_years="4.5",
            sex="Female",
            weight_kg="16",
            length_height_cm="102",
            measurement_position="height",
            oedema="no",
        )

        self.assertEqual(result["age_months"], "54")
        self.assertEqual(result["age_days"], 1644)
        self.assertEqual(len(result["indicators"]), 3)
        self.assertTrue(
            all(item["z_score"] != "Not calculated" for item in result["indicators"])
        )

    def test_rejects_age_above_five_years(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 5 years"):
            calculate_screening_by_age(
                age_years="5.1",
                sex="Female",
                weight_kg="16",
                length_height_cm="102",
                measurement_position="height",
                oedema="no",
            )

    def test_rejects_future_measurement_date(self):
        with self.assertRaisesRegex(ValueError, "cannot be in the future"):
            calculate_screening(
                birth_date=date(2025, 1, 1),
                measurement_date=date(2099, 1, 1),
                sex="Male",
                weight_kg="10",
                length_height_cm="80",
                measurement_position="height",
                oedema="no",
            )

    def test_loads_official_reference_tables(self):
        standards = load_growth_standards()

        self.assertEqual(len(standards.length_height_for_age), 3654)
        self.assertEqual(len(standards.weight_for_age), 3654)
        self.assertEqual(len(standards.weight_for_length_height), 2404)


if __name__ == "__main__":
    unittest.main()
