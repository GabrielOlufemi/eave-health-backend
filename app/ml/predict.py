import os
import pickle
import logging
import numpy as np
import joblib
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Model paths ───────────────────────────────────────────────────────────────

ML_DIR = Path(__file__).parent

_diabetes_model = None
_diabetes_scaler = None
_hypertension_model = None
_hypertension_scaler = None
_feature_columns = None


def _load_models():
    global _diabetes_model, _diabetes_scaler
    global _hypertension_model, _hypertension_scaler
    global _feature_columns

    if _feature_columns is not None:
        return  # already loaded

    logger.info("[ML] Loading models and scalers...")

    with open(ML_DIR / "feature_columns.pkl", "rb") as f:
        _feature_columns = pickle.load(f)

    _diabetes_model = joblib.load(ML_DIR / "diabetes_model.pkl")
    _diabetes_scaler = joblib.load(ML_DIR / "diabetes_scaler.pkl")
    _hypertension_model = joblib.load(ML_DIR / "hypertension_model.pkl")
    _hypertension_scaler = joblib.load(ML_DIR / "hypertension_scaler.pkl")

    logger.info(f"[ML] Models loaded. Feature count: {len(_feature_columns)}")


# ── Feature engineering ───────────────────────────────────────────────────────

def _calc_age(dob: str) -> int:
    try:
        birth = datetime.strptime(dob, "%Y-%m-%d")
        return (datetime.utcnow() - birth).days // 365
    except Exception:
        return 0


def _bmi_category(bmi: float) -> int:
    """0=underweight, 1=normal, 2=overweight, 3=obese"""
    if bmi < 18.5:
        return 0
    elif bmi < 25:
        return 1
    elif bmi < 30:
        return 2
    return 3


def _bp_category(systolic: float, diastolic: float) -> int:
    """0=normal, 1=elevated, 2=stage1, 3=stage2"""
    if systolic < 120 and diastolic < 80:
        return 0
    elif systolic < 130 and diastolic < 80:
        return 1
    elif systolic < 140 or diastolic < 90:
        return 2
    return 3


def _age_group(age: int) -> int:
    """0=<30, 1=30-44, 2=45-59, 3=60+"""
    if age < 30:
        return 0
    elif age < 45:
        return 1
    elif age < 60:
        return 2
    return 3


def _metabolic_risk(bmi: float, fasting_glucose: float, systolic: float) -> int:
    """Simple composite — 1 if 2+ risk factors elevated"""
    flags = 0
    if bmi >= 30:
        flags += 1
    if fasting_glucose >= 100:
        flags += 1
    if systolic >= 130:
        flags += 1
    return 1 if flags >= 2 else 0


def build_feature_vector(
    dob: str,
    sex: int,
    ethnicity: int,
    income_poverty_ratio: float,
    systolic_bp: float,
    diastolic_bp: float,
    bmi: float,
    waist_cm: float,
    fasting_glucose: float,
    hba1c: float,
    total_cholesterol: float,
    ever_smoked: int,
    alcohol_use: int,
    physically_active: int,
) -> dict:
    """
    Takes raw patient inputs and returns a fully engineered feature dict
    matching feature_columns.pkl order.
    """
    age = _calc_age(dob)

    # Engineered features
    glucose_hba1c_ratio = fasting_glucose / hba1c if hba1c else 0.0
    bmi_cat = _bmi_category(bmi)
    pulse_pressure = systolic_bp - diastolic_bp
    bp_cat = _bp_category(systolic_bp, diastolic_bp)
    age_grp = _age_group(age)
    met_risk = _metabolic_risk(bmi, fasting_glucose, systolic_bp)
    age_x_bmi = age * bmi
    bmi_x_inactive = bmi * (1 if not physically_active else 0)
    age_x_systolic = age * systolic_bp

    return {
        "age": age,
        "sex": sex,
        "ethnicity": ethnicity,
        "income_poverty_ratio": income_poverty_ratio,
        "systolic_bp": systolic_bp,
        "diastolic_bp": diastolic_bp,
        "bmi": bmi,
        "waist_cm": waist_cm,
        "fasting_glucose": fasting_glucose,
        "hba1c": hba1c,
        "total_cholesterol": total_cholesterol,
        "ever_smoked": ever_smoked,
        "alcohol_use": alcohol_use,
        "physically_active": physically_active,
        "glucose_hba1c_ratio": glucose_hba1c_ratio,
        "bmi_category": bmi_cat,
        "pulse_pressure": pulse_pressure,
        "bp_category": bp_cat,
        "age_group": age_grp,
        "metabolic_risk": met_risk,
        "age_x_bmi": age_x_bmi,
        "bmi_x_inactive": bmi_x_inactive,
        "age_x_systolic": age_x_systolic,
    }


# ── Inference ─────────────────────────────────────────────────────────────────

def run_predictions(feature_dict: dict) -> dict:
    """
    Takes a feature dict (from build_feature_vector) and returns:
    {
        "diabetes_risk": float,       # 0.0 - 1.0
        "hypertension_risk": float,   # 0.0 - 1.0
        "diabetes_label": str,        # low / moderate / high
        "hypertension_label": str,
        "engineered_features": dict,  # full snapshot for audit/storage
    }
    """
    _load_models()

    # Build array in correct column order
    X = np.array([[feature_dict[col] for col in _feature_columns]], dtype=float)

    # Scale + predict diabetes
    X_d = _diabetes_scaler.transform(X)
    diabetes_prob = float(_diabetes_model.predict_proba(X_d)[0][1])

    # Scale + predict hypertension
    X_h = _hypertension_scaler.transform(X)
    hypertension_prob = float(_hypertension_model.predict_proba(X_h)[0][1])

    def _label(prob: float) -> str:
        if prob < 0.35:
            return "low"
        elif prob < 0.65:
            return "moderate"
        return "high"

    logger.info(
        f"[ML] Predictions — diabetes: {diabetes_prob:.3f} ({_label(diabetes_prob)}), "
        f"hypertension: {hypertension_prob:.3f} ({_label(hypertension_prob)})"
    )

    return {
        "diabetes_risk": round(diabetes_prob, 4),
        "hypertension_risk": round(hypertension_prob, 4),
        "diabetes_label": _label(diabetes_prob),
        "hypertension_label": _label(hypertension_prob),
        "engineered_features": feature_dict,
    }


# ── Convenience wrapper ───────────────────────────────────────────────────────

def predict_from_patient_data(
    dob: str,
    sex: int,
    ethnicity: int = 3,
    income_poverty_ratio: float = 2.0,
    systolic_bp: float = 120.0,
    diastolic_bp: float = 80.0,
    weight_kg: float = 70.0,
    height_cm: float = 170.0,
    waist_cm: float = 85.0,
    fasting_glucose: float = 90.0,
    hba1c: float = 5.5,
    total_cholesterol: float = 180.0,
    ever_smoked: int = 0,
    alcohol_use: int = 0,
    physically_active: int = 1,
) -> dict:
    """
    Convenience wrapper — computes BMI from weight/height if not provided,
    then runs full feature engineering + inference.

    All parameters have safe defaults so partial data doesn't crash inference.
    """
    bmi = weight_kg / ((height_cm / 100) ** 2) if height_cm else 25.0

    features = build_feature_vector(
        dob=dob,
        sex=sex,
        ethnicity=ethnicity,
        income_poverty_ratio=income_poverty_ratio,
        systolic_bp=systolic_bp,
        diastolic_bp=diastolic_bp,
        bmi=bmi,
        waist_cm=waist_cm,
        fasting_glucose=fasting_glucose,
        hba1c=hba1c,
        total_cholesterol=total_cholesterol,
        ever_smoked=ever_smoked,
        alcohol_use=alcohol_use,
        physically_active=physically_active,
    )

    return run_predictions(features)