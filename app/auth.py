"""
auth.py — Password hashing, JWT tokens, patient code generation, and
           FastAPI dependencies for extracting the current user/medic.
"""

import os
import uuid
import random
import string
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User, Medic

# ── Config ────────────────────────────────────────────────────────────────────

JWT_SECRET    = os.environ.get("JWT_SECRET", "eave-health-jwt-secret-change-me")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRY    = int(os.environ.get("JWT_EXPIRY_HOURS", "72"))

bearer_scheme = HTTPBearer(auto_error=False)


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_token(subject_id: str, role: str) -> str:
    """Create a JWT with sub=<uuid>, role=patient|medic, exp=now+72h."""
    payload = {
        "sub": subject_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT.  Raises HTTPException on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Patient code generator ────────────────────────────────────────────────────

def generate_patient_code() -> str:
    """Generate a code like EAVE-8942-X (10 chars)."""
    digits = "".join(random.choices(string.digits, k=4))
    letter = random.choice(string.ascii_uppercase)
    return f"EAVE-{digits}-{letter}"


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and return the authenticated User from the JWT."""
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(creds.credentials)
    if payload.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Patient access required")

    result = await db.execute(
        select(User).where(User.user_id == uuid.UUID(payload["sub"]))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def get_current_medic(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Medic:
    """Extract and return the authenticated Medic from the JWT."""
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(creds.credentials)
    if payload.get("role") != "medic":
        raise HTTPException(status_code=403, detail="Medic access required")

    result = await db.execute(
        select(Medic).where(Medic.medic_id == uuid.UUID(payload["sub"]))
    )
    medic = result.scalar_one_or_none()
    if not medic:
        raise HTTPException(status_code=404, detail="Medic not found")
    return medic


async def get_current_any(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Return either a User or Medic — used for shared endpoints."""
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(creds.credentials)
    role = payload.get("role")
    uid  = uuid.UUID(payload["sub"])

    if role == "patient":
        result = await db.execute(select(User).where(User.user_id == uid))
        return result.scalar_one_or_none()
    elif role == "medic":
        result = await db.execute(select(Medic).where(Medic.medic_id == uid))
        return result.scalar_one_or_none()

    raise HTTPException(status_code=403, detail="Unknown role")
