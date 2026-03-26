"""
auth_router.py — Signup + Login for patients and medics.

POST /api/auth/signup   → create patient account, returns JWT + patient_code
POST /api/auth/login    → authenticate patient, returns JWT
POST /api/auth/medic/signup → create medic account, returns JWT
POST /api/auth/medic/login  → authenticate medic, returns JWT
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User, Medic, Hospital
from app.auth import (
    hash_password, verify_password, create_token, generate_patient_code,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class PatientSignup(BaseModel):
    full_name: str
    email: str
    password: str
    date_of_birth: str                     # YYYY-MM-DD
    sex: Optional[int] = None              # 1=Male, 2=Female
    ethnicity: Optional[int] = None
    location: Optional[str] = None
    blood_type: Optional[str] = None
    next_of_kin_email: Optional[str] = None


class MedicSignup(BaseModel):
    full_name: str
    email: str
    password: str
    specialty: Optional[str] = None
    hospital_name: Optional[str] = None
    department: Optional[str] = None
    room_number: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    role: str
    user_id: str
    patient_code: Optional[str] = None
    full_name: str


# ── Patient auth ──────────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse)
async def patient_signup(body: PatientSignup, db: AsyncSession = Depends(get_db)):
    # Check duplicate email
    exists = await db.execute(select(User).where(User.email == body.email))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Generate unique patient code
    code = generate_patient_code()
    while True:
        dup = await db.execute(select(User).where(User.patient_code == code))
        if not dup.scalar_one_or_none():
            break
        code = generate_patient_code()

    user = User(
        full_name=body.full_name,
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        patient_code=code,
        date_of_birth=date.fromisoformat(body.date_of_birth),
        sex=body.sex,
        ethnicity=body.ethnicity,
        location=body.location,
        blood_type=body.blood_type,
        next_of_kin_email=body.next_of_kin_email,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_token(str(user.user_id), "patient")
    return AuthResponse(
        token=token,
        role="patient",
        user_id=str(user.user_id),
        patient_code=user.patient_code,
        full_name=user.full_name,
    )


@router.post("/login", response_model=AuthResponse)
async def patient_login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == body.email.lower().strip())
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(str(user.user_id), "patient")
    return AuthResponse(
        token=token,
        role="patient",
        user_id=str(user.user_id),
        patient_code=user.patient_code,
        full_name=user.full_name,
    )


# ── Medic auth ────────────────────────────────────────────────────────────────

@router.post("/medic/signup", response_model=AuthResponse)
async def medic_signup(body: MedicSignup, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(select(Medic).where(Medic.email == body.email))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Optionally link to hospital by name
    hospital_id = None
    if body.hospital_name:
        h = await db.execute(
            select(Hospital).where(Hospital.name == body.hospital_name)
        )
        hospital = h.scalar_one_or_none()
        if hospital:
            hospital_id = hospital.hospital_id

    medic = Medic(
        full_name=body.full_name,
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        specialty=body.specialty,
        hospital_id=hospital_id,
        department=body.department,
        room_number=body.room_number,
    )
    db.add(medic)
    await db.commit()
    await db.refresh(medic)

    token = create_token(str(medic.medic_id), "medic")
    return AuthResponse(
        token=token,
        role="medic",
        user_id=str(medic.medic_id),
        full_name=medic.full_name,
    )


@router.post("/medic/login", response_model=AuthResponse)
async def medic_login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Medic).where(Medic.email == body.email.lower().strip())
    )
    medic = result.scalar_one_or_none()
    if not medic or not verify_password(body.password, medic.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(str(medic.medic_id), "medic")
    return AuthResponse(
        token=token,
        role="medic",
        user_id=str(medic.medic_id),
        full_name=medic.full_name,
    )
