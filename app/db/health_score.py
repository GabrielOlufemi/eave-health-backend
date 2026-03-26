"""
health_score.py — The 10-point health score calculator.
Extracted from model.py for import by medic_router.
"""


def calculate_health_score(
    hba1c: float,
    fasting_glucose: float,
    systolic_bp: float,
    diastolic_bp: float,
    ldl_cholesterol: float,
    triglycerides: float,
    bmi: float,
    waist_cm: float,
    sex: int,
    ever_smoked: int,
    physically_active: int,
) -> dict:

    breakdown = {
        "pillar_a": {},
        "pillar_b": {},
        "pillar_c": {},
        "pillar_d": {},
    }

    # Pillar A: Metabolic (max deduction 3.5)
    a_deduction = 0.0
    if hba1c >= 6.5:
        a_deduction += 3.00
        breakdown["pillar_a"]["hba1c"] = {"value": hba1c, "deduction": -3.00, "reason": "Diabetic range"}
    elif hba1c >= 5.7:
        a_deduction += 1.50
        breakdown["pillar_a"]["hba1c"] = {"value": hba1c, "deduction": -1.50, "reason": "Pre-diabetic range"}
    else:
        breakdown["pillar_a"]["hba1c"] = {"value": hba1c, "deduction": 0, "reason": "Normal"}

    if fasting_glucose > 100:
        a_deduction += 0.50
        breakdown["pillar_a"]["fasting_glucose"] = {"value": fasting_glucose, "deduction": -0.50, "reason": "Elevated fasting glucose"}
    else:
        breakdown["pillar_a"]["fasting_glucose"] = {"value": fasting_glucose, "deduction": 0, "reason": "Normal"}
    a_deduction = min(a_deduction, 3.5)

    # Pillar B: Cardiovascular (max deduction 3.0)
    b_deduction = 0.0
    if systolic_bp >= 140 or diastolic_bp >= 90:
        b_deduction += 2.00
        breakdown["pillar_b"]["blood_pressure"] = {"value": f"{systolic_bp}/{diastolic_bp}", "deduction": -2.00, "reason": "Stage 2 hypertension"}
    elif systolic_bp >= 130 or diastolic_bp >= 80:
        b_deduction += 1.00
        breakdown["pillar_b"]["blood_pressure"] = {"value": f"{systolic_bp}/{diastolic_bp}", "deduction": -1.00, "reason": "Stage 1 hypertension"}
    else:
        breakdown["pillar_b"]["blood_pressure"] = {"value": f"{systolic_bp}/{diastolic_bp}", "deduction": 0, "reason": "Normal"}

    if ldl_cholesterol > 130 or triglycerides > 150:
        b_deduction += 1.00
        breakdown["pillar_b"]["lipids"] = {"ldl": ldl_cholesterol, "triglycerides": triglycerides, "deduction": -1.00, "reason": "Elevated lipids"}
    else:
        breakdown["pillar_b"]["lipids"] = {"ldl": ldl_cholesterol, "triglycerides": triglycerides, "deduction": 0, "reason": "Normal"}
    b_deduction = min(b_deduction, 3.0)

    # Pillar C: Body Composition (max deduction 2.0)
    c_deduction = 0.0
    if bmi >= 30:
        c_deduction += 1.50
        breakdown["pillar_c"]["bmi"] = {"value": bmi, "deduction": -1.50, "reason": "Obese"}
    elif bmi >= 25:
        c_deduction += 0.50
        breakdown["pillar_c"]["bmi"] = {"value": bmi, "deduction": -0.50, "reason": "Overweight"}
    else:
        breakdown["pillar_c"]["bmi"] = {"value": bmi, "deduction": 0, "reason": "Normal"}

    waist_threshold = 102 if sex == 1 else 88
    if waist_cm > waist_threshold:
        c_deduction += 0.50
        breakdown["pillar_c"]["waist"] = {"value": waist_cm, "deduction": -0.50, "reason": "Elevated waist circumference"}
    else:
        breakdown["pillar_c"]["waist"] = {"value": waist_cm, "deduction": 0, "reason": "Normal"}
    c_deduction = min(c_deduction, 2.0)

    # Pillar D: Lifestyle (max deduction 1.5)
    d_deduction = 0.0
    if ever_smoked == 1:
        d_deduction += 1.00
        breakdown["pillar_d"]["smoking"] = {"deduction": -1.00, "reason": "Smoker"}
    else:
        breakdown["pillar_d"]["smoking"] = {"deduction": 0, "reason": "Non-smoker"}

    if physically_active == 0:
        d_deduction += 0.50
        breakdown["pillar_d"]["activity"] = {"deduction": -0.50, "reason": "Physically inactive"}
    else:
        breakdown["pillar_d"]["activity"] = {"deduction": 0, "reason": "Active"}
    d_deduction = min(d_deduction, 1.5)

    # Final score
    total_deduction = a_deduction + b_deduction + c_deduction + d_deduction
    score = max(1.00, round(10.00 - total_deduction, 2))

    breakdown["summary"] = {
        "pillar_a_deduction": -a_deduction,
        "pillar_b_deduction": -b_deduction,
        "pillar_c_deduction": -c_deduction,
        "pillar_d_deduction": -d_deduction,
        "total_deduction": -total_deduction,
        "final_score": score,
    }

    return {
        "score": score,
        "breakdown": breakdown,
    }
