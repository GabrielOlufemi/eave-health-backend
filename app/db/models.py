"""
models.py — SQLAlchemy ORM models for Eave Health.

Mirrors createeave-updated.sql exactly, including the new tables
(appointments, clinical_visits) and added columns (blood_type,
heart_rate, temperature, room_number, department).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ── Core User ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    user_id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_code      = Column(String(10), unique=True, nullable=False, index=True)
    full_name         = Column(String(100), nullable=False)
    email             = Column(String(150), unique=True, nullable=False, index=True)
    password_hash     = Column(String(255), nullable=False)
    date_of_birth     = Column(Date, nullable=False)
    sex               = Column(SmallInteger)           # 1=Male, 2=Female
    ethnicity         = Column(SmallInteger)
    location          = Column(String(100), index=True)
    income_poverty_ratio = Column(Numeric(5, 2))
    next_of_kin_email = Column(String(150))
    blood_type        = Column(String(5))              # e.g. 'O+', 'AB-'
    created_at        = Column(DateTime, default=datetime.utcnow)

    # relationships
    vitals            = relationship("Vital",          back_populates="user", cascade="all, delete-orphan")
    lab_results       = relationship("LabResult",      back_populates="user", cascade="all, delete-orphan")
    medical_tests     = relationship("MedicalTest",    back_populates="user", cascade="all, delete-orphan")
    conditions        = relationship("Condition",      back_populates="user", cascade="all, delete-orphan")
    medications       = relationship("Medication",     back_populates="user", cascade="all, delete-orphan")
    surgeries         = relationship("Surgery",        back_populates="user", cascade="all, delete-orphan")
    family_history    = relationship("FamilyHistory",  back_populates="user", cascade="all, delete-orphan")
    lifestyle_entries = relationship("Lifestyle",      back_populates="user", cascade="all, delete-orphan")
    risk_predictions  = relationship("RiskPrediction", back_populates="user", cascade="all, delete-orphan")
    health_scores     = relationship("HealthScore",    back_populates="user", cascade="all, delete-orphan")
    appointments      = relationship("Appointment",    back_populates="user", cascade="all, delete-orphan")
    clinical_visits   = relationship("ClinicalVisit",  back_populates="user", cascade="all, delete-orphan")


# ── Hospitals & Medics ────────────────────────────────────────────────────────

class Hospital(Base):
    __tablename__ = "hospitals"

    hospital_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name        = Column(String(150), nullable=False)
    location    = Column(String(150), index=True)
    phone       = Column(String(20))
    email       = Column(String(150))
    created_at  = Column(DateTime, default=datetime.utcnow)

    medics = relationship("Medic", back_populates="hospital")


class Medic(Base):
    __tablename__ = "medics"

    medic_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id   = Column(UUID(as_uuid=True), ForeignKey("hospitals.hospital_id", ondelete="SET NULL"), index=True)
    full_name     = Column(String(100), nullable=False)
    email         = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    specialty     = Column(String(100), index=True)
    room_number   = Column(String(20))
    department    = Column(String(100))
    created_at    = Column(DateTime, default=datetime.utcnow)

    hospital    = relationship("Hospital", back_populates="medics")
    appointments = relationship("Appointment", back_populates="medic")
    clinical_visits = relationship("ClinicalVisit", back_populates="medic")


# ── Health Metrics ────────────────────────────────────────────────────────────

class Vital(Base):
    __tablename__ = "vitals"

    vitals_id    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    recorded_at  = Column(DateTime, default=datetime.utcnow, index=True)
    systolic_bp  = Column(Numeric(5, 1))
    diastolic_bp = Column(Numeric(5, 1))
    bmi          = Column(Numeric(5, 2))
    waist_cm     = Column(Numeric(5, 1))
    weight_kg    = Column(Numeric(5, 2))
    height_cm    = Column(Numeric(5, 2))
    heart_rate   = Column(Numeric(5, 1))
    temperature  = Column(Numeric(4, 2))

    user = relationship("User", back_populates="vitals")


class LabResult(Base):
    __tablename__ = "lab_results"

    lab_id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    recorded_at       = Column(DateTime, default=datetime.utcnow, index=True)
    fasting_glucose   = Column(Numeric(6, 2))
    hba1c             = Column(Numeric(4, 2))
    total_cholesterol = Column(Numeric(6, 2))
    ldl_cholesterol   = Column(Numeric(6, 2))
    triglycerides     = Column(Numeric(6, 2))

    user = relationship("User", back_populates="lab_results")


class MedicalTest(Base):
    __tablename__ = "medical_tests"

    test_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id       = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    test_name     = Column(String(150), nullable=False, index=True)
    test_type     = Column(String(50), index=True)
    ordered_reason = Column(Text)
    outcome       = Column(Text)
    clinical_note = Column(Text)
    performed_at  = Column(Date, index=True)
    location      = Column(String(150))
    created_at    = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="medical_tests")


class Condition(Base):
    __tablename__ = "conditions"

    condition_id   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    condition_name = Column(String(150), nullable=False, index=True)
    icd_code       = Column(String(20), index=True)
    diagnosed_at   = Column(Date, index=True)
    is_active      = Column(Boolean, default=True, index=True)
    notes          = Column(Text)

    user = relationship("User", back_populates="conditions")


class Medication(Base):
    __tablename__ = "medications"

    medication_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id       = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    drug_name     = Column(String(150), nullable=False, index=True)
    dosage        = Column(String(50))
    frequency     = Column(String(50))
    started_at    = Column(Date)
    ended_at      = Column(Date)
    prescribed_by = Column(String(100))

    user = relationship("User", back_populates="medications")


class Surgery(Base):
    __tablename__ = "surgeries"

    surgery_id   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    surgery_name = Column(String(150), nullable=False)
    performed_at = Column(Date)
    hospital     = Column(String(150))
    notes        = Column(Text)
    created_at   = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="surgeries")


class FamilyHistory(Base):
    __tablename__ = "family_history"

    entry_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    relation       = Column(String(50))
    condition_name = Column(String(150), nullable=False)
    notes          = Column(Text)

    user = relationship("User", back_populates="family_history")


# ── Lifestyle & Analytics ─────────────────────────────────────────────────────

class Lifestyle(Base):
    __tablename__ = "lifestyle"

    lifestyle_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    recorded_at       = Column(DateTime, default=datetime.utcnow, index=True)
    ever_smoked       = Column(SmallInteger)
    alcohol_use       = Column(SmallInteger)
    physically_active = Column(SmallInteger)
    diet_quality      = Column(SmallInteger)
    sleep_hours       = Column(Numeric(3, 1))

    user = relationship("User", back_populates="lifestyle_entries")


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"

    prediction_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id             = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    predicted_at        = Column(DateTime, default=datetime.utcnow, index=True)
    diabetes_risk       = Column(Numeric(5, 4))
    hypertension_risk   = Column(Numeric(5, 4))
    model_version       = Column(String(20), index=True)
    age                 = Column(SmallInteger)
    sex                 = Column(SmallInteger)
    bmi                 = Column(Numeric(5, 2))
    systolic_bp         = Column(Numeric(5, 1))
    diastolic_bp        = Column(Numeric(5, 1))
    fasting_glucose     = Column(Numeric(6, 2))
    hba1c               = Column(Numeric(4, 2))
    total_cholesterol   = Column(Numeric(6, 2))
    waist_cm            = Column(Numeric(5, 1))
    ever_smoked         = Column(SmallInteger)
    alcohol_use         = Column(SmallInteger)
    physically_active   = Column(SmallInteger)
    glucose_hba1c_ratio = Column(Numeric(8, 4))
    bmi_category        = Column(SmallInteger)
    pulse_pressure      = Column(Numeric(5, 1))
    bp_category         = Column(SmallInteger)
    age_group           = Column(SmallInteger)
    metabolic_risk      = Column(SmallInteger)
    age_x_bmi           = Column(Numeric(8, 2))
    bmi_x_inactive      = Column(Numeric(8, 2))
    age_x_systolic      = Column(Numeric(8, 2))

    user = relationship("User", back_populates="risk_predictions")


class HealthScore(Base):
    __tablename__ = "health_scores"

    score_id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    scored_at       = Column(DateTime, default=datetime.utcnow, index=True)
    score           = Column(Numeric(5, 2), index=True)
    score_breakdown = Column(JSONB)

    user = relationship("User", back_populates="health_scores")


# ── Appointments & Clinical Visits ────────────────────────────────────────────

class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    medic_id       = Column(UUID(as_uuid=True), ForeignKey("medics.medic_id", ondelete="SET NULL"), index=True)
    scheduled_at   = Column(DateTime, nullable=False, index=True)
    room_number    = Column(String(20))
    department     = Column(String(100))
    reason         = Column(Text)
    status         = Column(String(20), default="scheduled")  # scheduled|completed|cancelled|no_show
    created_at     = Column(DateTime, default=datetime.utcnow)

    user  = relationship("User",  back_populates="appointments")
    medic = relationship("Medic", back_populates="appointments")
    clinical_visit = relationship("ClinicalVisit", back_populates="appointment", uselist=False)


class ClinicalVisit(Base):
    __tablename__ = "clinical_visits"

    visit_id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id            = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    medic_id           = Column(UUID(as_uuid=True), ForeignKey("medics.medic_id", ondelete="SET NULL"), index=True)
    appointment_id     = Column(UUID(as_uuid=True), ForeignKey("appointments.appointment_id", ondelete="SET NULL"))
    visited_at         = Column(DateTime, default=datetime.utcnow)
    diagnosis_notes    = Column(Text)
    prescription_notes = Column(Text)
    clinical_notes     = Column(Text)

    user        = relationship("User",        back_populates="clinical_visits")
    medic       = relationship("Medic",        back_populates="clinical_visits")
    appointment = relationship("Appointment",  back_populates="clinical_visit")
