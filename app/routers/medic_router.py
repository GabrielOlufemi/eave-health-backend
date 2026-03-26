"""
medic_router.py — Provider/institution-facing endpoints.

Requires a valid medic JWT.
Prefix: /api/medic
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import (
    User,
    Medic,
    Vital,
    LabResult,
    Condition,
    Medication,
    Appointment,
    ClinicalVisit,
    MedicalTest,
    HealthScore,
    RiskPrediction,
    Lifestyle,
    Surgery,
    FamilyHistory,
)
from app.auth import get_current_medic

router = APIRouter(prefix="/api/medic", tags=["Medic"])


def _serialize(obj, fields: list[str]) -> dict:
    d = {}
    for f in fields:
        v = getattr(obj, f, None)
        if isinstance(v, UUID):
            d[f] = str(v)
        elif isinstance(v, (datetime, date)):
            d[f] = v.isoformat()
        elif isinstance(v, Decimal):
            d[f] = float(v)
        else:
            d[f] = v
    return d


# ── Patient Lookup by Code ────────────────────────────────────────────────────


@router.get("/lookup/{patient_code}")
async def lookup_patient(
    patient_code: str,
    medic: Medic = Depends(get_current_medic),
    db: AsyncSession = Depends(get_db),
):
    """
    Look up a patient by their EAVE-XXXX-X code.
    Returns their full medical record.
    """
    result = await db.execute(
        select(User).where(User.patient_code == patient_code.upper())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Patient not found")

    uid = user.user_id

    # Vitals
    vr = await db.execute(
        select(Vital)
        .where(Vital.user_id == uid)
        .order_by(desc(Vital.recorded_at))
        .limit(10)
    )
    vitals = [
        _serialize(
            v,
            [
                "vitals_id",
                "recorded_at",
                "systolic_bp",
                "diastolic_bp",
                "bmi",
                "waist_cm",
                "weight_kg",
                "height_cm",
                "heart_rate",
                "temperature",
            ],
        )
        for v in vr.scalars().all()
    ]

    # Labs
    lr = await db.execute(
        select(LabResult)
        .where(LabResult.user_id == uid)
        .order_by(desc(LabResult.recorded_at))
        .limit(10)
    )
    labs = [
        _serialize(
            l,
            [
                "lab_id",
                "recorded_at",
                "fasting_glucose",
                "hba1c",
                "total_cholesterol",
                "ldl_cholesterol",
                "triglycerides",
            ],
        )
        for l in lr.scalars().all()
    ]

    # Conditions
    cr = await db.execute(select(Condition).where(Condition.user_id == uid))
    conditions = [
        _serialize(
            c,
            [
                "condition_id",
                "condition_name",
                "icd_code",
                "diagnosed_at",
                "is_active",
                "notes",
            ],
        )
        for c in cr.scalars().all()
    ]

    # Medications
    mr = await db.execute(select(Medication).where(Medication.user_id == uid))
    medications = [
        _serialize(
            m,
            [
                "medication_id",
                "drug_name",
                "dosage",
                "frequency",
                "started_at",
                "ended_at",
                "prescribed_by",
            ],
        )
        for m in mr.scalars().all()
    ]

    # Surgeries
    sr = await db.execute(
        select(Surgery)
        .where(Surgery.user_id == uid)
        .order_by(desc(Surgery.performed_at))
    )
    surgeries = [
        _serialize(
            s,
            [
                "surgery_id",
                "surgery_name",
                "performed_at",
                "hospital",
                "notes",
            ],
        )
        for s in sr.scalars().all()
    ]

    # Family history
    fhr = await db.execute(select(FamilyHistory).where(FamilyHistory.user_id == uid))
    family = [
        _serialize(
            fh,
            [
                "entry_id",
                "relation",
                "condition_name",
                "notes",
            ],
        )
        for fh in fhr.scalars().all()
    ]

    # Tests
    tr = await db.execute(
        select(MedicalTest)
        .where(MedicalTest.user_id == uid)
        .order_by(desc(MedicalTest.performed_at))
        .limit(10)
    )
    tests = [
        _serialize(
            t,
            [
                "test_id",
                "test_name",
                "test_type",
                "ordered_reason",
                "outcome",
                "clinical_note",
                "performed_at",
                "location",
            ],
        )
        for t in tr.scalars().all()
    ]

    # Appointments
    ar = await db.execute(
        select(Appointment)
        .where(Appointment.user_id == uid)
        .order_by(desc(Appointment.scheduled_at))
        .limit(10)
    )
    appointments = [
        _serialize(
            a,
            [
                "appointment_id",
                "scheduled_at",
                "room_number",
                "department",
                "reason",
                "status",
            ],
        )
        for a in ar.scalars().all()
    ]

    # Latest health score
    hsr = await db.execute(
        select(HealthScore)
        .where(HealthScore.user_id == uid)
        .order_by(desc(HealthScore.scored_at))
        .limit(1)
    )
    scores = [
        _serialize(
            hs,
            [
                "score_id",
                "scored_at",
                "score",
                "score_breakdown",
            ],
        )
        for hs in hsr.scalars().all()
    ]

    # Latest lifestyle
    lsr = await db.execute(
        select(Lifestyle)
        .where(Lifestyle.user_id == uid)
        .order_by(desc(Lifestyle.recorded_at))
        .limit(1)
    )
    lifestyle = [
        _serialize(
            ls,
            [
                "lifestyle_id",
                "recorded_at",
                "ever_smoked",
                "alcohol_use",
                "physically_active",
                "diet_quality",
                "sleep_hours",
            ],
        )
        for ls in lsr.scalars().all()
    ]

    return {
        "patient": _serialize(
            user,
            [
                "user_id",
                "patient_code",
                "full_name",
                "email",
                "date_of_birth",
                "sex",
                "ethnicity",
                "location",
                "blood_type",
                "next_of_kin_email",
                "created_at",
            ],
        ),
        "vitals": vitals,
        "labs": labs,
        "conditions": conditions,
        "medications": medications,
        "surgeries": surgeries,
        "family_history": family,
        "tests": tests,
        "appointments": appointments,
        "health_scores": scores,
        "lifestyle": lifestyle,
    }


# ── Record Vitals (Nurse intake) ─────────────────────────────────────────────


class NurseVitalsIn(BaseModel):
    patient_code: str
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    heart_rate: Optional[float] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    temperature: Optional[float] = None
    waist_cm: Optional[float] = None
    notes: Optional[str] = None


@router.post("/vitals")
async def record_vitals(
    body: NurseVitalsIn,
    medic: Medic = Depends(get_current_medic),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.patient_code == body.patient_code.upper())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Compute BMI if weight and height given
    bmi = None
    if body.weight_kg and body.height_cm and body.height_cm > 0:
        bmi = body.weight_kg / ((body.height_cm / 100) ** 2)

    v = Vital(
        user_id=user.user_id,
        systolic_bp=body.systolic_bp,
        diastolic_bp=body.diastolic_bp,
        heart_rate=body.heart_rate,
        weight_kg=body.weight_kg,
        height_cm=body.height_cm,
        temperature=body.temperature,
        waist_cm=body.waist_cm,
        bmi=round(bmi, 2) if bmi else None,
    )
    db.add(v)
    await db.commit()
    return {"status": "recorded", "vitals_id": str(v.vitals_id)}


# ── Log Clinical Visit ───────────────────────────────────────────────────────

import asyncio
import logging as _logging

_visit_logger = _logging.getLogger(__name__)


class PrescriptionIn(BaseModel):
    drug_name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None  # e.g. "7 days", "ongoing"
    instructions: Optional[str] = None


class VisitLogIn(BaseModel):
    patient_code: str
    appointment_id: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    prescription_notes: Optional[str] = None  # free-text summary (kept for compat)
    clinical_notes: Optional[str] = None
    prescriptions: list[PrescriptionIn] = []  # ← NEW: structured prescriptions
    tests: list[dict] = []  # ← NEW: test results from this visit


@router.post("/visit")
async def log_visit(
    body: VisitLogIn,
    medic: Medic = Depends(get_current_medic),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.patient_code == body.patient_code.upper())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Patient not found")

    appt_id = None
    if body.appointment_id:
        appt_id = UUID(body.appointment_id)
        ar = await db.execute(
            select(Appointment).where(Appointment.appointment_id == appt_id)
        )
        appt = ar.scalar_one_or_none()
        if appt:
            appt.status = "completed"

    visit = ClinicalVisit(
        user_id=user.user_id,
        medic_id=medic.medic_id,
        appointment_id=appt_id,
        diagnosis_notes=body.diagnosis_notes,
        prescription_notes=body.prescription_notes,
        clinical_notes=body.clinical_notes,
    )
    db.add(visit)

    # ── Write structured prescriptions to medications table ──────────────────
    today = date.today()
    for rx in body.prescriptions:
        med = Medication(
            user_id=user.user_id,
            drug_name=rx.drug_name,
            dosage=rx.dosage,
            frequency=rx.frequency,
            prescribed_by=medic.full_name,
            started_at=today,
            # ended_at stays None (active) unless duration implies otherwise
        )
        db.add(med)

    await db.commit()
    await db.refresh(visit)

    # ── Fire orchestrator pipeline (non-blocking) ────────────────────────────
    if body.prescriptions:
        asyncio.create_task(_fire_orchestrator(user, medic, body, str(visit.visit_id)))

    return {
        "status": "logged",
        "visit_id": str(visit.visit_id),
        "prescriptions_written": len(body.prescriptions),
        "orchestrator_triggered": len(body.prescriptions) > 0,
    }


async def _fire_orchestrator(user, medic, body: VisitLogIn, visit_id: str):
    """
    Calls the orchestrator post-appointment pipeline after a visit is logged.
    Runs as a background task so it doesn't block the API response.
    Handles errors gracefully — a failed email must never break the visit log.
    """
    try:
        from app.api.orchestrator import (
            PatientProfile,
            PostAppointmentPayload,
            VitalsReading,
            Prescription,
            TestResult,
            handle_post_appointment,
            store,
        )

        # Build PatientProfile for the orchestrator
        patient = PatientProfile(
            patient_id=str(user.user_id),
            full_name=user.full_name,
            email=user.email,
            dob=user.date_of_birth.isoformat() if user.date_of_birth else "1990-01-01",
            allergies=[],
            medical_conditions=[],
            next_of_kin_name=None,
            next_of_kin_email=user.next_of_kin_email or None,
        )
        # Keep orchestrator's in-memory store in sync so analytics works too
        store["patients"][str(user.user_id)] = patient

        # Map prescriptions
        rx_list = [
            Prescription(
                drug_name=rx.drug_name,
                dosage=rx.dosage or "",
                frequency=rx.frequency or "",
                duration=rx.duration,
                instructions=rx.instructions,
            )
            for rx in body.prescriptions
        ]

        # Map any tests passed in
        test_list = [
            TestResult(
                test_name=t.get("test_name", "Unknown"),
                outcome=t.get("outcome", ""),
                date=t.get("date", date.today().isoformat()),
            )
            for t in body.tests
        ]

        payload = PostAppointmentPayload(
            appointment_id=body.appointment_id or visit_id,
            patient_id=str(user.user_id),
            doctor_name=medic.full_name,
            institution_name=medic.department or "Eave Health",
            prescriptions=rx_list,
            tests=test_list,
            doctor_notes=body.clinical_notes,
            completed_at=datetime.utcnow().isoformat(),
        )

        await handle_post_appointment(payload)
        _visit_logger.info(
            f"[VISIT] Orchestrator pipeline complete for {user.full_name} "
            f"— {len(rx_list)} prescription(s)"
        )

    except Exception as exc:
        # Log but never raise — the visit is already committed to DB
        _visit_logger.error(
            f"[VISIT] Orchestrator pipeline failed for {user.full_name}: {exc}",
            exc_info=True,
        )


# ── Schedule Appointment ──────────────────────────────────────────────────────


class ApptIn(BaseModel):
    patient_code: str
    scheduled_at: str  # ISO datetime
    room_number: Optional[str] = None
    department: Optional[str] = None
    reason: Optional[str] = None


@router.post("/appointment")
async def schedule_appointment(
    body: ApptIn,
    medic: Medic = Depends(get_current_medic),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.patient_code == body.patient_code.upper())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Patient not found")

    appt = Appointment(
        user_id=user.user_id,
        medic_id=medic.medic_id,
        scheduled_at=datetime.fromisoformat(body.scheduled_at),
        room_number=body.room_number or medic.room_number,
        department=body.department or medic.department,
        reason=body.reason,
    )
    db.add(appt)
    await db.commit()
    await db.refresh(appt)

    # Send appointment confirmation email (non-blocking)
    asyncio.create_task(_send_appointment_email(user, medic, appt, body))

    return {"status": "scheduled", "appointment_id": str(appt.appointment_id)}


async def _send_appointment_email(user, medic, appt, body):
    """Send appointment confirmation email via orchestrator (runs as background task)."""
    try:
        from app.api.orchestrator import send_email
        dt = appt.scheduled_at
        date_str = dt.strftime("%A, %d %B %Y")
        time_str = dt.strftime("%I:%M %p")
        doctor_line = f"Doctor: Dr. {medic.full_name}\n" if medic.full_name else ""
        dept_line   = f"Department: {body.department or medic.department}\n" if (body.department or medic.department) else ""
        room_line   = f"Room: {body.room_number or medic.room_number}\n" if (body.room_number or medic.room_number) else ""
        reason_line = f"Reason: {body.reason}\n" if body.reason else ""

        subject = f"Appointment Confirmed — {body.department or medic.department or 'Eave Health'}"
        email_body = (
            f"Hi {user.full_name.split()[0]},\n\n"
            f"Your appointment has been scheduled.\n\n"
            f"Date: {date_str}\n"
            f"Time: {time_str}\n"
            + doctor_line + dept_line + room_line + reason_line +
            "\nIf you need to reschedule, please reply to this email.\n\n— Eave"
        )

        from app.api.orchestrator import send_email_async
        await send_email_async(user.email, subject, email_body)
        _visit_logger.info(f"[APPT] Confirmation email sent to {user.email}")
    except Exception as exc:
        _visit_logger.error(f"[APPT] Failed to send confirmation email: {exc}", exc_info=True)


# ── Add Medical Test ──────────────────────────────────────────────────────────


class TestIn(BaseModel):
    patient_code: str
    test_name: str
    test_type: Optional[str] = None
    ordered_reason: Optional[str] = None
    outcome: Optional[str] = None
    clinical_note: Optional[str] = None
    performed_at: Optional[str] = None
    location: Optional[str] = None


@router.post("/test")
async def add_test(
    body: TestIn,
    medic: Medic = Depends(get_current_medic),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.patient_code == body.patient_code.upper())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Patient not found")

    data = body.model_dump(exclude={"patient_code"}, exclude_none=True)
    if "performed_at" in data:
        data["performed_at"] = date.fromisoformat(data["performed_at"])
    test = MedicalTest(user_id=user.user_id, **data)
    db.add(test)
    await db.commit()
    return {"status": "recorded", "test_id": str(test.test_id)}


# ── Run ML Prediction ────────────────────────────────────────────────────────


@router.post("/predict/{patient_code}")
async def run_prediction(
    patient_code: str,
    medic: Medic = Depends(get_current_medic),
    db: AsyncSession = Depends(get_db),
):
    """
    Pull latest data for a patient from DB, run ML prediction,
    store the result, and return it.
    """
    result = await db.execute(
        select(User).where(User.patient_code == patient_code.upper())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Patient not found")

    uid = user.user_id

    # Get latest vitals
    vr = await db.execute(
        select(Vital)
        .where(Vital.user_id == uid)
        .order_by(desc(Vital.recorded_at))
        .limit(1)
    )
    vital = vr.scalar_one_or_none()

    # Get latest labs
    lr = await db.execute(
        select(LabResult)
        .where(LabResult.user_id == uid)
        .order_by(desc(LabResult.recorded_at))
        .limit(1)
    )
    lab = lr.scalar_one_or_none()

    # Get latest lifestyle
    lsr = await db.execute(
        select(Lifestyle)
        .where(Lifestyle.user_id == uid)
        .order_by(desc(Lifestyle.recorded_at))
        .limit(1)
    )
    lifestyle = lsr.scalar_one_or_none()

    if not vital or not lab:
        raise HTTPException(
            status_code=422,
            detail="Insufficient data — need at least one vitals and one lab record.",
        )

    from app.ml.predict import predict_from_patient_data

    pred_result = predict_from_patient_data(
        dob=user.date_of_birth.isoformat(),
        sex=user.sex or 1,
        ethnicity=user.ethnicity or 3,
        income_poverty_ratio=float(user.income_poverty_ratio or 2.0),
        systolic_bp=float(vital.systolic_bp or 120),
        diastolic_bp=float(vital.diastolic_bp or 80),
        weight_kg=float(vital.weight_kg or 70),
        height_cm=float(vital.height_cm or 170),
        waist_cm=float(vital.waist_cm or 85),
        fasting_glucose=float(lab.fasting_glucose or 90),
        hba1c=float(lab.hba1c or 5.5),
        total_cholesterol=float(lab.total_cholesterol or 180),
        ever_smoked=int(lifestyle.ever_smoked or 0) if lifestyle else 0,
        alcohol_use=int(lifestyle.alcohol_use or 0) if lifestyle else 0,
        physically_active=int(lifestyle.physically_active or 1) if lifestyle else 1,
    )

    # Store prediction
    features = pred_result["engineered_features"]
    rp = RiskPrediction(
        user_id=uid,
        diabetes_risk=pred_result["diabetes_risk"],
        hypertension_risk=pred_result["hypertension_risk"],
        model_version="v1.0",
        age=features.get("age"),
        sex=features.get("sex"),
        bmi=features.get("bmi"),
        systolic_bp=features.get("systolic_bp"),
        diastolic_bp=features.get("diastolic_bp"),
        fasting_glucose=features.get("fasting_glucose"),
        hba1c=features.get("hba1c"),
        total_cholesterol=features.get("total_cholesterol"),
        waist_cm=features.get("waist_cm"),
        ever_smoked=features.get("ever_smoked"),
        alcohol_use=features.get("alcohol_use"),
        physically_active=features.get("physically_active"),
        glucose_hba1c_ratio=features.get("glucose_hba1c_ratio"),
        bmi_category=features.get("bmi_category"),
        pulse_pressure=features.get("pulse_pressure"),
        bp_category=features.get("bp_category"),
        age_group=features.get("age_group"),
        metabolic_risk=features.get("metabolic_risk"),
        age_x_bmi=features.get("age_x_bmi"),
        bmi_x_inactive=features.get("bmi_x_inactive"),
        age_x_systolic=features.get("age_x_systolic"),
    )
    db.add(rp)
    await db.commit()

    return {
        "status": "predicted",
        "diabetes_risk": pred_result["diabetes_risk"],
        "diabetes_label": pred_result["diabetes_label"],
        "hypertension_risk": pred_result["hypertension_risk"],
        "hypertension_label": pred_result["hypertension_label"],
        "prediction_id": str(rp.prediction_id),
    }


# ── Compute Health Score ──────────────────────────────────────────────────────


@router.post("/health-score/{patient_code}")
async def compute_health_score(
    patient_code: str,
    medic: Medic = Depends(get_current_medic),
    db: AsyncSession = Depends(get_db),
):
    """Pull latest data, compute health score, store and return."""
    result = await db.execute(
        select(User).where(User.patient_code == patient_code.upper())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Patient not found")

    uid = user.user_id

    vr = await db.execute(
        select(Vital)
        .where(Vital.user_id == uid)
        .order_by(desc(Vital.recorded_at))
        .limit(1)
    )
    vital = vr.scalar_one_or_none()

    lr = await db.execute(
        select(LabResult)
        .where(LabResult.user_id == uid)
        .order_by(desc(LabResult.recorded_at))
        .limit(1)
    )
    lab = lr.scalar_one_or_none()

    lsr = await db.execute(
        select(Lifestyle)
        .where(Lifestyle.user_id == uid)
        .order_by(desc(Lifestyle.recorded_at))
        .limit(1)
    )
    lifestyle = lsr.scalar_one_or_none()

    if not vital or not lab:
        raise HTTPException(
            status_code=422, detail="Insufficient data — need vitals and labs."
        )

    # Import the score calculator from the uploaded model.py
    from app.db.health_score import calculate_health_score

    score_result = calculate_health_score(
        hba1c=float(lab.hba1c or 5.0),
        fasting_glucose=float(lab.fasting_glucose or 90),
        systolic_bp=float(vital.systolic_bp or 120),
        diastolic_bp=float(vital.diastolic_bp or 80),
        ldl_cholesterol=float(lab.ldl_cholesterol or 100),
        triglycerides=float(lab.triglycerides or 120),
        bmi=float(vital.bmi or 25),
        waist_cm=float(vital.waist_cm or 85),
        sex=user.sex or 1,
        ever_smoked=int(lifestyle.ever_smoked or 0) if lifestyle else 0,
        physically_active=int(lifestyle.physically_active or 1) if lifestyle else 1,
    )

    hs = HealthScore(
        user_id=uid,
        score=score_result["score"],
        score_breakdown=score_result["breakdown"],
    )
    db.add(hs)
    await db.commit()

    return {
        "status": "scored",
        "score": score_result["score"],
        "breakdown": score_result["breakdown"],
        "score_id": str(hs.score_id),
    }