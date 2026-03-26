"""
patient_router.py — All patient-facing CRUD endpoints.

Every endpoint requires a valid patient JWT.
Prefix: /api/patient
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import (
    User, Vital, LabResult, Condition, Medication, Surgery,
    FamilyHistory, Lifestyle, RiskPrediction, HealthScore,
    Appointment, MedicalTest, ClinicalVisit, Medic,
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/patient", tags=["Patient"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(obj, fields: list[str]) -> dict:
    """Quick serializer — converts UUID/Decimal/date/datetime to strings."""
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


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    return _serialize(user, [
        "user_id", "patient_code", "full_name", "email",
        "date_of_birth", "sex", "ethnicity", "location",
        "income_poverty_ratio", "next_of_kin_email", "blood_type", "created_at",
    ])


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    location: Optional[str] = None
    next_of_kin_email: Optional[str] = None
    blood_type: Optional[str] = None
    income_poverty_ratio: Optional[float] = None


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(user, field, val)
    await db.commit()
    return {"status": "updated"}


# ── Vitals ────────────────────────────────────────────────────────────────────

class VitalIn(BaseModel):
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    bmi: Optional[float] = None
    waist_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    heart_rate: Optional[float] = None
    temperature: Optional[float] = None


VITAL_FIELDS = [
    "vitals_id", "user_id", "recorded_at",
    "systolic_bp", "diastolic_bp", "bmi", "waist_cm",
    "weight_kg", "height_cm", "heart_rate", "temperature",
]


@router.post("/vitals")
async def add_vitals(
    body: VitalIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    v = Vital(user_id=user.user_id, **body.model_dump(exclude_none=True))
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return _serialize(v, VITAL_FIELDS)


@router.get("/vitals")
async def list_vitals(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Vital)
        .where(Vital.user_id == user.user_id)
        .order_by(desc(Vital.recorded_at))
        .limit(limit)
    )
    return [_serialize(v, VITAL_FIELDS) for v in result.scalars().all()]


# ── Lab Results ───────────────────────────────────────────────────────────────

class LabIn(BaseModel):
    fasting_glucose: Optional[float] = None
    hba1c: Optional[float] = None
    total_cholesterol: Optional[float] = None
    ldl_cholesterol: Optional[float] = None
    triglycerides: Optional[float] = None


LAB_FIELDS = [
    "lab_id", "user_id", "recorded_at",
    "fasting_glucose", "hba1c", "total_cholesterol",
    "ldl_cholesterol", "triglycerides",
]


@router.post("/labs")
async def add_lab(
    body: LabIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lab = LabResult(user_id=user.user_id, **body.model_dump(exclude_none=True))
    db.add(lab)
    await db.commit()
    await db.refresh(lab)
    return _serialize(lab, LAB_FIELDS)


@router.get("/labs")
async def list_labs(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LabResult)
        .where(LabResult.user_id == user.user_id)
        .order_by(desc(LabResult.recorded_at))
        .limit(limit)
    )
    return [_serialize(l, LAB_FIELDS) for l in result.scalars().all()]


# ── Conditions ────────────────────────────────────────────────────────────────

class ConditionIn(BaseModel):
    condition_name: str
    icd_code: Optional[str] = None
    diagnosed_at: Optional[str] = None
    is_active: bool = True
    notes: Optional[str] = None


COND_FIELDS = [
    "condition_id", "user_id", "condition_name", "icd_code",
    "diagnosed_at", "is_active", "notes",
]


@router.post("/conditions")
async def add_condition(
    body: ConditionIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_none=True)
    if "diagnosed_at" in data:
        data["diagnosed_at"] = date.fromisoformat(data["diagnosed_at"])
    c = Condition(user_id=user.user_id, **data)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _serialize(c, COND_FIELDS)


@router.get("/conditions")
async def list_conditions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Condition)
        .where(Condition.user_id == user.user_id)
        .order_by(desc(Condition.diagnosed_at))
    )
    return [_serialize(c, COND_FIELDS) for c in result.scalars().all()]


# ── Medications ───────────────────────────────────────────────────────────────

class MedIn(BaseModel):
    drug_name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    prescribed_by: Optional[str] = None


MED_FIELDS = [
    "medication_id", "user_id", "drug_name", "dosage",
    "frequency", "started_at", "ended_at", "prescribed_by",
]


@router.post("/medications")
async def add_medication(
    body: MedIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_none=True)
    for df in ("started_at", "ended_at"):
        if df in data:
            data[df] = date.fromisoformat(data[df])
    m = Medication(user_id=user.user_id, **data)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _serialize(m, MED_FIELDS)


@router.get("/medications")
async def list_medications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Medication)
        .where(Medication.user_id == user.user_id)
        .order_by(desc(Medication.started_at))
    )
    return [_serialize(m, MED_FIELDS) for m in result.scalars().all()]


# ── Surgeries ─────────────────────────────────────────────────────────────────

class SurgeryIn(BaseModel):
    surgery_name: str
    performed_at: Optional[str] = None
    hospital: Optional[str] = None
    notes: Optional[str] = None


SURG_FIELDS = [
    "surgery_id", "user_id", "surgery_name",
    "performed_at", "hospital", "notes", "created_at",
]


@router.post("/surgeries")
async def add_surgery(
    body: SurgeryIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_none=True)
    if "performed_at" in data:
        data["performed_at"] = date.fromisoformat(data["performed_at"])
    s = Surgery(user_id=user.user_id, **data)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _serialize(s, SURG_FIELDS)


@router.get("/surgeries")
async def list_surgeries(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Surgery)
        .where(Surgery.user_id == user.user_id)
        .order_by(desc(Surgery.performed_at))
    )
    return [_serialize(s, SURG_FIELDS) for s in result.scalars().all()]


# ── Family History ────────────────────────────────────────────────────────────

class FamHistIn(BaseModel):
    relation: Optional[str] = None
    condition_name: str
    notes: Optional[str] = None


FAM_FIELDS = ["entry_id", "user_id", "relation", "condition_name", "notes"]


@router.post("/family-history")
async def add_family_history(
    body: FamHistIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fh = FamilyHistory(user_id=user.user_id, **body.model_dump(exclude_none=True))
    db.add(fh)
    await db.commit()
    await db.refresh(fh)
    return _serialize(fh, FAM_FIELDS)


@router.get("/family-history")
async def list_family_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FamilyHistory).where(FamilyHistory.user_id == user.user_id)
    )
    return [_serialize(fh, FAM_FIELDS) for fh in result.scalars().all()]


# ── Lifestyle ─────────────────────────────────────────────────────────────────

class LifestyleIn(BaseModel):
    ever_smoked: Optional[int] = None
    alcohol_use: Optional[int] = None
    physically_active: Optional[int] = None
    diet_quality: Optional[int] = None
    sleep_hours: Optional[float] = None


LIFE_FIELDS = [
    "lifestyle_id", "user_id", "recorded_at",
    "ever_smoked", "alcohol_use", "physically_active",
    "diet_quality", "sleep_hours",
]


@router.post("/lifestyle")
async def add_lifestyle(
    body: LifestyleIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ls = Lifestyle(user_id=user.user_id, **body.model_dump(exclude_none=True))
    db.add(ls)
    await db.commit()
    await db.refresh(ls)
    return _serialize(ls, LIFE_FIELDS)


@router.get("/lifestyle")
async def list_lifestyle(
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Lifestyle)
        .where(Lifestyle.user_id == user.user_id)
        .order_by(desc(Lifestyle.recorded_at))
        .limit(limit)
    )
    return [_serialize(ls, LIFE_FIELDS) for ls in result.scalars().all()]


# ── Medical Tests ─────────────────────────────────────────────────────────────

TEST_FIELDS = [
    "test_id", "user_id", "test_name", "test_type",
    "ordered_reason", "outcome", "clinical_note",
    "performed_at", "location", "created_at",
]


@router.get("/tests")
async def list_tests(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MedicalTest)
        .where(MedicalTest.user_id == user.user_id)
        .order_by(desc(MedicalTest.performed_at))
        .limit(limit)
    )
    return [_serialize(t, TEST_FIELDS) for t in result.scalars().all()]


# ── Appointments ──────────────────────────────────────────────────────────────

APPT_FIELDS = [
    "appointment_id", "user_id", "medic_id", "scheduled_at",
    "room_number", "department", "reason", "status", "created_at",
]


@router.get("/appointments")
async def list_appointments(
    status: Optional[str] = None,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Appointment).where(Appointment.user_id == user.user_id)
    if status:
        q = q.where(Appointment.status == status)
    q = q.order_by(desc(Appointment.scheduled_at)).limit(limit)
    result = await db.execute(q)
    appointments = []
    for a in result.scalars().all():
        data = _serialize(a, APPT_FIELDS)
        # Attach medic name if available
        if a.medic_id:
            m = await db.execute(select(Medic).where(Medic.medic_id == a.medic_id))
            medic = m.scalar_one_or_none()
            if medic:
                data["medic_name"] = medic.full_name
                data["medic_specialty"] = medic.specialty
        appointments.append(data)
    return appointments


# ── Health Scores ─────────────────────────────────────────────────────────────

SCORE_FIELDS = ["score_id", "user_id", "scored_at", "score", "score_breakdown"]


@router.get("/health-scores")
async def list_health_scores(
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HealthScore)
        .where(HealthScore.user_id == user.user_id)
        .order_by(desc(HealthScore.scored_at))
        .limit(limit)
    )
    return [_serialize(hs, SCORE_FIELDS) for hs in result.scalars().all()]


# ── Risk Predictions ──────────────────────────────────────────────────────────

PRED_FIELDS = [
    "prediction_id", "user_id", "predicted_at",
    "diabetes_risk", "hypertension_risk", "model_version",
]


@router.get("/predictions")
async def list_predictions(
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RiskPrediction)
        .where(RiskPrediction.user_id == user.user_id)
        .order_by(desc(RiskPrediction.predicted_at))
        .limit(limit)
    )
    return [_serialize(p, PRED_FIELDS) for p in result.scalars().all()]


# ── Clinical Visit Notes ─────────────────────────────────────────────────────

VISIT_FIELDS = [
    "visit_id", "user_id", "medic_id", "appointment_id",
    "visited_at", "diagnosis_notes", "prescription_notes", "clinical_notes",
]


@router.get("/visits")
async def list_visits(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ClinicalVisit)
        .where(ClinicalVisit.user_id == user.user_id)
        .order_by(desc(ClinicalVisit.visited_at))
        .limit(limit)
    )
    visits = []
    for cv in result.scalars().all():
        data = _serialize(cv, VISIT_FIELDS)
        if cv.medic_id:
            m = await db.execute(select(Medic).where(Medic.medic_id == cv.medic_id))
            medic = m.scalar_one_or_none()
            if medic:
                data["medic_name"] = medic.full_name
        visits.append(data)
    return visits


# ── Dashboard aggregate — single call for the whole dashboard ─────────────────

@router.get("/dashboard")
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns everything the frontend dashboard needs in one shot."""

    # Latest vitals
    vr = await db.execute(
        select(Vital).where(Vital.user_id == user.user_id)
        .order_by(desc(Vital.recorded_at)).limit(3)
    )
    vitals = [_serialize(v, VITAL_FIELDS) for v in vr.scalars().all()]

    # Latest labs
    lr = await db.execute(
        select(LabResult).where(LabResult.user_id == user.user_id)
        .order_by(desc(LabResult.recorded_at)).limit(1)
    )
    labs = [_serialize(l, LAB_FIELDS) for l in lr.scalars().all()]

    # Active conditions
    cr = await db.execute(
        select(Condition).where(
            Condition.user_id == user.user_id,
            Condition.is_active == True,
        )
    )
    conditions = [_serialize(c, COND_FIELDS) for c in cr.scalars().all()]

    # Active medications (no ended_at)
    mr = await db.execute(
        select(Medication).where(
            Medication.user_id == user.user_id,
            Medication.ended_at == None,
        )
    )
    medications = [_serialize(m, MED_FIELDS) for m in mr.scalars().all()]

    # Upcoming appointments — only future ones, ordered soonest first
    ar = await db.execute(
        select(Appointment).where(
            Appointment.user_id == user.user_id,
            Appointment.status == "scheduled",
            Appointment.scheduled_at >= datetime.utcnow(),
        ).order_by(Appointment.scheduled_at).limit(3)
    )
    appointments_raw = ar.scalars().all()
    appointments = []
    for a in appointments_raw:
        data = _serialize(a, APPT_FIELDS)
        if a.medic_id:
            m = await db.execute(select(Medic).where(Medic.medic_id == a.medic_id))
            medic = m.scalar_one_or_none()
            if medic:
                data["medic_name"] = medic.full_name
                data["medic_specialty"] = medic.specialty
        appointments.append(data)

    # Latest health score
    sr = await db.execute(
        select(HealthScore).where(HealthScore.user_id == user.user_id)
        .order_by(desc(HealthScore.scored_at)).limit(1)
    )
    scores = [_serialize(s, SCORE_FIELDS) for s in sr.scalars().all()]

    # Latest prediction
    pr = await db.execute(
        select(RiskPrediction).where(RiskPrediction.user_id == user.user_id)
        .order_by(desc(RiskPrediction.predicted_at)).limit(1)
    )
    predictions = [_serialize(p, PRED_FIELDS) for p in pr.scalars().all()]

    # Recent clinical visits (for prescription notes added by the doctor)
    cvr = await db.execute(
        select(ClinicalVisit)
        .where(ClinicalVisit.user_id == user.user_id)
        .order_by(desc(ClinicalVisit.visited_at))
        .limit(5)
    )
    clinical_visits = []
    for cv in cvr.scalars().all():
        data = _serialize(cv, VISIT_FIELDS)
        if cv.medic_id:
            m = await db.execute(select(Medic).where(Medic.medic_id == cv.medic_id))
            medic = m.scalar_one_or_none()
            if medic:
                data["medic_name"] = medic.full_name
        clinical_visits.append(data)

    return {
        "profile": _serialize(user, [
            "user_id", "patient_code", "full_name", "email",
            "date_of_birth", "sex", "blood_type",
        ]),
        "vitals": vitals,
        "labs": labs,
        "conditions": conditions,
        "medications": medications,
        "appointments": appointments,
        "health_scores": scores,
        "predictions": predictions,
        "clinical_visits": clinical_visits,
    }