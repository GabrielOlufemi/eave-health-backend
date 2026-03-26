"""
seed_providers.py — Seeds medic accounts for each registered hospital.

Run after seed_hospitals.py:
    python seed_providers.py

All accounts share the same password: black&Tan123$
"""

import os
import bcrypt
import sqlalchemy
from dotenv import load_dotenv

load_dotenv()

e = sqlalchemy.create_engine(os.environ["DATABASE_URL_SYNC"])

PASSWORD = "black&Tan123$"
password_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()

providers = [
    {
        "full_name": "Dr. Adeyemi Okoro",
        "email": "admin@afriglobal.med",
        "specialty": "Internal Medicine",
        "department": "General Practice",
        "hospital_name": "Afriglobal Medicare",
    },
    {
        "full_name": "Dr. Funke Adeniyi",
        "email": "admin@ancilla.med",
        "specialty": "Cardiology",
        "department": "Cardiology",
        "hospital_name": "Ancilla Hospital",
    },
    {
        "full_name": "Dr. Chioma Eze",
        "email": "admin@duchess.med",
        "specialty": "Obstetrics & Gynaecology",
        "department": "Women's Health",
        "hospital_name": "Duchess Hospital",
    },
    {
        "full_name": "Dr. Tunde Bakare",
        "email": "admin@buth.med",
        "specialty": "Family Medicine",
        "department": "General Practice",
        "hospital_name": "Babcock University Teaching Hospital",
    },
]

with e.begin() as conn:
    for p in providers:
        # Check if medic already exists
        exists = conn.execute(
            sqlalchemy.text("SELECT medic_id FROM medics WHERE email = :email"),
            {"email": p["email"]},
        ).fetchone()

        if exists:
            print(f"Already exists: {p['email']}")
            continue

        # Find the hospital_id
        hospital = conn.execute(
            sqlalchemy.text("SELECT hospital_id FROM hospitals WHERE name = :name"),
            {"name": p["hospital_name"]},
        ).fetchone()

        hospital_id = hospital[0] if hospital else None

        conn.execute(
            sqlalchemy.text(
                "INSERT INTO medics (full_name, email, password_hash, specialty, department, hospital_id) "
                "VALUES (:full_name, :email, :password_hash, :specialty, :department, :hospital_id)"
            ),
            {
                "full_name": p["full_name"],
                "email": p["email"],
                "password_hash": password_hash,
                "specialty": p["specialty"],
                "department": p["department"],
                "hospital_id": hospital_id,
            },
        )
        print(f"Seeded: {p['full_name']} ({p['email']}) → {p['hospital_name']}")

print(f"\nDone. All providers share password: {PASSWORD}")
print("\nLogin credentials:")
for p in providers:
    print(f"  {p['hospital_name']:45s} → {p['email']}")