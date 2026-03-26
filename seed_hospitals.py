"""
seed_hospitals.py — Run once to:
  1. Add hospital_id column to appointments table
  2. Seed the 4 registered institutions

Usage:
    python seed_hospitals.py
"""

import os
import sqlalchemy
from dotenv import load_dotenv

load_dotenv()

e = sqlalchemy.create_engine(os.environ["DATABASE_URL_SYNC"])

# Step 1: Add hospital_id to appointments if not exists
stmts = [
    "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS hospital_id UUID REFERENCES hospitals(hospital_id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_appointments_hospital_id ON appointments(hospital_id)",
]

for s in stmts:
    with e.begin() as c:
        c.execute(sqlalchemy.text(s))
        print(f"OK: {s[:60]}...")

# Step 2: Seed hospitals
hospitals = [
    {
        "name": "Afriglobal Medicare",
        "location": "Victoria Island, Lagos",
        "phone": "+234 1 271 7500",
        "email": "info@afriglobalmedicare.com",
    },
    {
        "name": "Ancilla Hospital",
        "location": "Lekki, Lagos",
        "phone": "+234 1 453 0000",
        "email": "contact@ancillahospital.com",
    },
    {
        "name": "Duchess International Hospital",
        "location": "Ikeja GRA, Lagos",
        "phone": "+234 1 700 0000",
        "email": "info@duchessinternational.com",
    },
    {
        "name": "Babcock University Teaching Hospital",
        "location": "Ilishan-Remo, Ogun State",
        "phone": "+234 805 000 0000",
        "email": "info@buth.edu.ng",
    },
]

for h in hospitals:
    with e.begin() as c:
        result = c.execute(
            sqlalchemy.text("SELECT hospital_id FROM hospitals WHERE name = :name"),
            {"name": h["name"]},
        )
        if result.fetchone():
            print(f"SKIP: {h['name']} already exists")
            continue

        c.execute(
            sqlalchemy.text(
                "INSERT INTO hospitals (name, location, phone, email) "
                "VALUES (:name, :location, :phone, :email)"
            ),
            h,
        )
        print(f"SEED: {h['name']}")

# Verify
with e.begin() as c:
    result = c.execute(
        sqlalchemy.text("SELECT hospital_id, name, location FROM hospitals")
    )
    rows = result.fetchall()
    print(f"\n--- {len(rows)} hospitals in DB ---")
    for r in rows:
        print(f"  {r[0]}  {r[1]}  ({r[2]})")

print("\nDone.")
