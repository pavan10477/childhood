"""WHO Child Growth Standards screening calculations for children under five."""

import csv
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path


REFERENCE_DIR = Path(__file__).resolve().parent / "data" / "who_growth_standards"
LAST_REFERENCE_AGE_DAYS = 1826
WHO_DAYS_PER_MONTH = Decimal("30.4375")
LMS = tuple[float, float, float]


@dataclass(frozen=True)
class GrowthStandards:
    length_height_for_age: dict[tuple[int, int], LMS]
    weight_for_age: dict[tuple[int, int], LMS]
    weight_for_length_height: dict[tuple[int, int, str], LMS]


def _load_tsv(
    filename: str, index_fields: tuple[str, ...], measure_field: str | None = None
) -> dict[tuple[object, ...], LMS]:
    path = REFERENCE_DIR / filename
    with path.open(encoding="utf-8", newline="") as reference_file:
        rows = csv.DictReader(reference_file, delimiter="\t")
        expected = set(index_fields) | {"l", "m", "s"}
        if rows.fieldnames is None or not expected.issubset(rows.fieldnames):
            raise RuntimeError(f"WHO reference file has an unexpected format: {path}")

        table: dict[tuple[object, ...], LMS] = {}
        for row in rows:
            key_values: list[object] = []
            for field in index_fields:
                value = row[field]
                if field == "sex":
                    key_values.append(int(value))
                elif field == "age":
                    key_values.append(int(value))
                elif field == measure_field:
                    key_values.append(int(round(float(value) * 10)))
                else:
                    key_values.append(value)
            key = tuple(key_values)
            if key in table:
                raise RuntimeError(f"Duplicate WHO reference entry in {path}: {key}")
            table[key] = (float(row["l"]), float(row["m"]), float(row["s"]))

    if not table:
        raise RuntimeError(f"WHO reference file contains no rows: {path}")
    return table


@lru_cache(maxsize=1)
def load_growth_standards() -> GrowthStandards:
    length_height_for_age = _load_tsv("lenanthro.txt", ("sex", "age"))
    weight_for_age = _load_tsv("weianthro.txt", ("sex", "age"))

    weight_for_length_height = _load_tsv(
        "wflanthro.txt", ("sex", "length", "lorh"), measure_field="length"
    )
    weight_for_length_height.update(
        _load_tsv(
            "wfhanthro.txt", ("sex", "height", "lorh"), measure_field="height"
        )
    )
    return GrowthStandards(
        length_height_for_age=length_height_for_age,
        weight_for_age=weight_for_age,
        weight_for_length_height=weight_for_length_height,
    )


def _parse_positive_decimal(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError(f"Enter a valid {label}.") from None
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{label.capitalize()} must be greater than zero.")
    try:
        if not math.isfinite(float(parsed)):
            raise ValueError(f"Enter a finite {label} value.")
    except OverflowError:
        raise ValueError(f"Enter a finite {label} value.") from None
    return parsed


def _compute_zscore(value: float, lms: LMS, adjust_extremes: bool) -> float:
    l, m, s = lms
    if l == 0:
        z_score = math.log(value / m) / s
    else:
        z_score = ((value / m) ** l - 1) / (l * s)

    if not adjust_extremes or -3 <= z_score <= 3:
        return z_score

    def value_at_standard_deviations(standard_deviations: int) -> float:
        if l == 0:
            return m * math.exp(s * standard_deviations)
        return m * (1 + l * s * standard_deviations) ** (1 / l)

    if z_score > 3:
        sd3 = value_at_standard_deviations(3)
        sd2 = value_at_standard_deviations(2)
        z_score = 3 + (value - sd3) / (sd3 - sd2)
    else:
        sd3 = value_at_standard_deviations(-3)
        sd2 = value_at_standard_deviations(-2)
        z_score = -3 + (value - sd3) / (sd2 - sd3)
    return z_score


def _weight_for_length_height_lms(
    standards: GrowthStandards, sex: int, mode: str, measurement_cm: Decimal
) -> LMS | None:
    scaled_value = measurement_cm * 10
    lower_tick = int(scaled_value)
    fraction = float(scaled_value - lower_tick)
    lower = standards.weight_for_length_height.get((sex, lower_tick, mode))
    if lower is None:
        return None
    if fraction == 0:
        return lower

    upper = standards.weight_for_length_height.get((sex, lower_tick + 1, mode))
    if upper is None:
        return None
    interpolated = tuple(
        low + fraction * (high - low) for low, high in zip(lower, upper)
    )
    return interpolated[0], interpolated[1], interpolated[2]


def _indicator(name: str, z_score: float, status: str) -> dict[str, str]:
    return {"name": name, "z_score": f"{z_score:.2f}", "status": status}


def _height_status(z_score: float) -> str:
    if z_score < -3:
        return "Stunting: Yes"
    if z_score < -2:
        return "Stunting: Yes"
    return "Stunting: No"


def _weight_status(z_score: float) -> str:
    if z_score < -2:
        return "Underweight: Yes"
    return "Underweight: No"


def _weight_for_length_height_status(z_score: float) -> str:
    if z_score < -2:
        return "Wasting: Yes"
    if z_score > 3:
        return "Overweight: Yes"
    if z_score > 2:
        return "Overweight: Yes"
    return "Wasting/overweight: No"


def _precaution(name: str, status: str) -> str:
    if status.startswith(("Not calculated", "WHO reference range")):
        return (
            "This result is unavailable for the recorded measurements. Ask a "
            "qualified health professional to review the child's growth."
        )
    if name == "Length/height-for-age":
        if status.startswith("Stunting: Yes"):
            return (
                "Give a balanced diet with eggs, dal, milk or curd, vegetables "
                "and other locally available nutritious foods appropriate for "
                "the child's age."
            )
        return (
            "No stunting concern was flagged. Continue varied, balanced meals "
            "and routine height monitoring."
        )
    if name == "Weight-for-age":
        if status.startswith("Underweight: Yes"):
            return (
                "Offer regular, age-appropriate meals with energy-rich nutritious "
                "foods, such as rice, dal, eggs and suitable nut pastes where safe."
            )
        return (
            "No underweight concern was flagged. Continue balanced, "
            "age-appropriate meals and routine weight monitoring."
        )
    if status.startswith("Wasting: Yes"):
        return (
            "Provide nutritious food appropriate for the child's age; feed the "
            "child regularly; maintain good hygiene; monitor the child's growth."
        )
    if status.startswith("Overweight: Yes"):
        return (
            "Discuss the child's growth with a qualified health professional. "
            "Offer balanced, age-appropriate meals and avoid restrictive diets."
        )
    return (
        "No wasting or overweight concern was flagged. Continue balanced, "
        "age-appropriate meals and routine growth monitoring."
    )


def _report_details(indicator: dict[str, str]) -> dict[str, str]:
    name = indicator["name"]
    status = indicator["status"]
    if status.startswith(("Not calculated", "WHO reference range")):
        indicator["concern_level"] = "Unable to assess"
        indicator["meaning"] = (
            "This growth indicator could not be calculated from the available "
            "reference data."
        )
    elif name == "Length/height-for-age":
        has_concern = status == "Stunting: Yes"
        indicator["concern_level"] = "High Concern" if has_concern else "Low Concern"
        indicator["meaning"] = (
            "Height is low for age."
            if has_concern
            else "No stunting concern was identified by this screening."
        )
    elif name == "Weight-for-age":
        has_concern = status == "Underweight: Yes"
        indicator["concern_level"] = "High Concern" if has_concern else "Low Concern"
        indicator["meaning"] = (
            "Weight is low for age."
            if has_concern
            else "No underweight concern was identified by this screening."
        )
    elif status == "Wasting: Yes":
        indicator["concern_level"] = "High Concern"
        indicator["meaning"] = "Weight is low for height."
    elif status == "Overweight: Yes":
        indicator["concern_level"] = "High Concern"
        indicator["meaning"] = "Weight is high for height."
    else:
        indicator["concern_level"] = "Low Concern"
        indicator["meaning"] = (
            "No wasting or overweight concern was identified by this screening."
        )
    indicator["precaution"] = _precaution(name, status)
    return indicator


def calculate_screening(
    *,
    birth_date: date,
    measurement_date: date,
    sex: str,
    weight_kg: str,
    length_height_cm: str,
    measurement_position: str,
    oedema: str,
) -> dict[str, object]:
    if measurement_date < birth_date:
        raise ValueError("Measurement date cannot be earlier than the birth date.")
    if measurement_date > date.today():
        raise ValueError("Measurement date cannot be in the future.")

    age_days = (measurement_date - birth_date).days
    if age_days > LAST_REFERENCE_AGE_DAYS:
        raise ValueError(
            "WHO screening is available only through the last reference age "
            f"({LAST_REFERENCE_AGE_DAYS} days, approximately 5 years)."
        )

    sex_code = {"Male": 1, "Female": 2}.get(sex)
    if sex_code is None:
        raise ValueError("Select the child's sex used by the WHO growth reference.")
    if measurement_position not in {"length", "height"}:
        raise ValueError("Select whether the measurement was taken lying down or standing.")
    if oedema not in {"no", "yes", "unsure"}:
        raise ValueError("Select an option for bilateral pitting oedema.")

    weight = _parse_positive_decimal(weight_kg, "weight")
    stature = _parse_positive_decimal(length_height_cm, "length or height")
    standards = load_growth_standards()
    indicators: list[dict[str, str]] = []

    adjustment = 0.7 if age_days < 731 and measurement_position == "height" else 0.0
    if age_days >= 731 and measurement_position == "length":
        adjustment = -0.7
    standardized_stature = stature + Decimal(str(adjustment))

    length_height_lms = standards.length_height_for_age.get((sex_code, age_days))
    if length_height_lms is None:
        raise RuntimeError(f"No WHO length/height-for-age reference for day {age_days}.")
    height_z = _compute_zscore(float(standardized_stature), length_height_lms, False)
    indicators.append(_indicator("Length/height-for-age", height_z, _height_status(height_z)))

    if oedema == "no":
        weight_age_lms = standards.weight_for_age.get((sex_code, age_days))
        if weight_age_lms is None:
            raise RuntimeError(f"No WHO weight-for-age reference for day {age_days}.")
        weight_z = _compute_zscore(float(weight), weight_age_lms, True)
        indicators.append(_indicator("Weight-for-age", weight_z, _weight_status(weight_z)))

        reference_mode = "L" if age_days < 731 else "H"
        weight_length_height_lms = _weight_for_length_height_lms(
            standards, sex_code, reference_mode, standardized_stature
        )
        if weight_length_height_lms is None:
            valid_range = "45–110 cm" if reference_mode == "L" else "65–120 cm"
            indicators.append(
                {
                    "name": "Weight-for-length/height",
                    "z_score": "Not calculated",
                    "status": f"WHO reference range for this measurement is {valid_range}.",
                }
            )
        else:
            weight_length_height_z = _compute_zscore(
                float(weight), weight_length_height_lms, True
            )
            indicators.append(
                _indicator(
                    "Weight-for-length/height",
                    weight_length_height_z,
                    _weight_for_length_height_status(weight_length_height_z),
                )
            )
    else:
        status = (
            "Not calculated because oedema was reported."
            if oedema == "yes"
            else "Not calculated because oedema status is unknown."
        )
        for name in ("Weight-for-age", "Weight-for-length/height"):
            indicators.append(
                {"name": name, "z_score": "Not calculated", "status": status}
            )

    indicators = [_report_details(indicator) for indicator in indicators]

    return {
        "age_days": age_days,
        "indicators": indicators,
        "position_adjustment_cm": f"{adjustment:+.1f}",
        "standardized_measurement_cm": f"{standardized_stature:.1f}",
    }


def calculate_screening_by_age(
    *,
    age_years: str,
    sex: str,
    weight_kg: str,
    length_height_cm: str,
    measurement_position: str | None = None,
    oedema: str,
) -> dict[str, object]:
    try:
        years = Decimal(age_years)
    except (InvalidOperation, TypeError):
        raise ValueError("Enter the child's age in years.") from None
    if not years.is_finite() or years < 0 or years > 5:
        raise ValueError("Age must be between 0 and 5 years.")

    age_months = years * 12
    age_days = int(
        (age_months * WHO_DAYS_PER_MONTH).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if age_days > LAST_REFERENCE_AGE_DAYS:
        raise ValueError(
            "WHO screening is available only through the last reference age "
            f"({LAST_REFERENCE_AGE_DAYS} days, approximately 5 years)."
        )
    if measurement_position is None:
        measurement_position = "length" if age_days < 731 else "height"

    measurement_date = date.today()
    result = calculate_screening(
        birth_date=measurement_date - timedelta(days=age_days),
        measurement_date=measurement_date,
        sex=sex,
        weight_kg=weight_kg,
        length_height_cm=length_height_cm,
        measurement_position=measurement_position,
        oedema=oedema,
    )
    result["age_months"] = format(age_months.normalize(), "f")
    result["age_years"] = format(years.normalize(), "f")
    result["gender"] = sex
    result["height_cm"] = length_height_cm
    result["weight_kg"] = weight_kg
    display_order = (
        "Length/height-for-age",
        "Weight-for-length/height",
        "Weight-for-age",
    )
    report_indicators = [
        next(item for item in result["indicators"] if item["name"] == name)
        for name in display_order
    ]
    result["report_indicators"] = report_indicators
    if any(item["concern_level"] == "High Concern" for item in report_indicators):
        result["overall_concern"] = "HIGH NUTRITIONAL CONCERN"
    elif any(item["concern_level"] == "Unable to assess" for item in report_indicators):
        result["overall_concern"] = "ASSESSMENT INCOMPLETE"
    else:
        result["overall_concern"] = "LOW NUTRITIONAL CONCERN"
    return result
