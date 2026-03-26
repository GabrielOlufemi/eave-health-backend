"""
seed_demo_data.py — seeds demo medical history for one specific patient.
Set DEMO_EMAIL below, then run:  python seed_demo_data.py
"""

import os, sys
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

import sqlalchemy
from sqlalchemy import text

e = sqlalchemy.create_engine(os.environ["DATABASE_URL_SYNC"])

# ── Set this to your demo account email ───────────────────────────────────────
DEMO_EMAIL = "kusorogabriel@gmail.com"
# ─────────────────────────────────────────────────────────────────────────────


def run(conn, sql, params):
    conn.execute(text(sql), params)


with e.connect() as c:
    row = c.execute(
        text("SELECT user_id, full_name, patient_code FROM users WHERE email = :email"),
        {"email": DEMO_EMAIL},
    ).fetchone()

    if not row:
        print(f"No user found with email: {DEMO_EMAIL}")
        sys.exit(1)

    user_id = str(row[0])
    full_name = row[1]
    code = row[2]
    print(f"Seeding: {full_name} ({code})")

    medic_row = c.execute(
        text(
            "SELECT m.medic_id, m.full_name FROM medics m "
            "JOIN hospitals h ON h.hospital_id = m.hospital_id "
            "WHERE h.name ILIKE '%afriglobal%' LIMIT 1"
        )
    ).fetchone()
    medic_id = str(medic_row[0]) if medic_row else None
    medic_name = medic_row[1] if medic_row else "Dr. Adeyemi Okoro"

    hosp_row = c.execute(
        text(
            "SELECT hospital_id FROM hospitals WHERE name ILIKE '%afriglobal%' LIMIT 1"
        )
    ).fetchone()
    hospital_id = str(hosp_row[0]) if hosp_row else None

with e.begin() as c:

    vitals_data = [
        (11, 148, 96, 84, 88.0, 175.0, 96.0, 37.1),
        (9, 144, 93, 82, 87.2, 175.0, 95.0, 36.9),
        (7, 138, 90, 80, 86.5, 175.0, 94.0, 37.0),
        (5, 134, 87, 78, 85.8, 175.0, 92.5, 36.8),
        (3, 128, 84, 76, 84.2, 175.0, 91.0, 37.0),
        (1, 122, 80, 72, 83.0, 175.0, 89.5, 36.7),
    ]
    for months_ago, sys_bp, dia_bp, hr, weight, height, waist, temp in vitals_data:
        recorded = datetime.now() - timedelta(days=months_ago * 30)
        bmi = round(weight / ((height / 100) ** 2), 2)
        run(
            c,
            "INSERT INTO vitals (user_id, systolic_bp, diastolic_bp, heart_rate, weight_kg, height_cm, waist_cm, bmi, temperature, recorded_at) "
            "VALUES (:uid, :sys, :dia, :hr, :w, :h, :wst, :bmi, :tmp, :rec)",
            dict(
                uid=user_id,
                sys=sys_bp,
                dia=dia_bp,
                hr=hr,
                w=weight,
                h=height,
                wst=waist,
                bmi=bmi,
                tmp=temp,
                rec=recorded,
            ),
        )
    print("✓ Vitals seeded (6 entries)")

    labs_data = [
        (10, 118, 6.2, 212, 142, 168),
        (7, 112, 6.0, 208, 138, 155),
        (4, 105, 5.8, 204, 132, 140),
        (1, 98, 5.6, 196, 125, 128),
    ]
    for months_ago, gluc, hba1c, chol, ldl, trig in labs_data:
        recorded = datetime.now() - timedelta(days=months_ago * 30)
        run(
            c,
            "INSERT INTO lab_results (user_id, fasting_glucose, hba1c, total_cholesterol, ldl_cholesterol, triglycerides, recorded_at) "
            "VALUES (:uid, :g, :h, :tc, :ldl, :trig, :rec)",
            dict(
                uid=user_id, g=gluc, h=hba1c, tc=chol, ldl=ldl, trig=trig, rec=recorded
            ),
        )
    print("✓ Lab results seeded (4 entries)")

    conditions = [
        (
            "Hypertension Stage 1",
            "I10",
            date.today() - timedelta(days=365),
            True,
            "Actively managed with Amlodipine. BP trending down consistently over 12 months.",
        ),
        (
            "Pre-diabetes (IFG)",
            "R73.01",
            date.today() - timedelta(days=300),
            True,
            "Fasting glucose 98-118 mg/dL range. HbA1c improving. Managed with lifestyle modification.",
        ),
    ]
    for name, icd, diag_date, active, notes in conditions:
        run(
            c,
            "INSERT INTO conditions (user_id, condition_name, icd_code, diagnosed_at, is_active, notes) "
            "VALUES (:uid, :n, :icd, :diag, :act, :notes)",
            dict(uid=user_id, n=name, icd=icd, diag=diag_date, act=active, notes=notes),
        )
    print("✓ Conditions seeded (2 entries)")

    meds = [
        (
            "Amlodipine",
            "5mg",
            "Once daily",
            medic_name,
            date.today() - timedelta(days=365),
            None,
        ),
        (
            "Metformin",
            "500mg",
            "Twice daily",
            medic_name,
            date.today() - timedelta(days=300),
            None,
        ),
        (
            "Lisinopril",
            "10mg",
            "Once daily",
            medic_name,
            date.today() - timedelta(days=400),
            date.today() - timedelta(days=365),
        ),
    ]
    for drug, dosage, freq, prescribed_by, started, ended in meds:
        run(
            c,
            "INSERT INTO medications (user_id, drug_name, dosage, frequency, prescribed_by, started_at, ended_at) "
            "VALUES (:uid, :drug, :dos, :freq, :presc, :s, :en)",
            dict(
                uid=user_id,
                drug=drug,
                dos=dosage,
                freq=freq,
                presc=prescribed_by,
                s=started,
                en=ended,
            ),
        )
    print("✓ Medications seeded (3 entries)")

    family = [
        ("Father", "Hypertension", "Diagnosed in his 40s. Managed with medication."),
        ("Mother", "Type 2 Diabetes", "Diagnosed at 52. On insulin therapy."),
        ("Paternal Uncle", "Stroke", "Suffered ischaemic stroke at age 61."),
    ]
    for relation, condition, notes in family:
        run(
            c,
            "INSERT INTO family_history (user_id, relation, condition_name, notes) VALUES (:uid, :rel, :cond, :notes)",
            dict(uid=user_id, rel=relation, cond=condition, notes=notes),
        )
    print("✓ Family history seeded (3 entries)")

    print("✓ Family history seeded (3 entries)")

    run(
        c,  # ← indented, inside the with block
        "INSERT INTO lifestyle (user_id, ever_smoked, alcohol_use, physically_active, diet_quality, sleep_hours, recorded_at) "
        "VALUES (:uid, :ever_smoked, :alcohol_use, :physically_active, 3, 7.0, :rec)",
        dict(
            uid=user_id,
            ever_smoked=0,
            alcohol_use=0,
            physically_active=1,
            rec=datetime.now() - timedelta(days=30),
        ),
    )
    print("✓ Lifestyle seeded")

    tests = [
        (
            "Electrocardiogram (ECG)",
            "Cardiology",
            "Baseline following hypertension diagnosis",
            "Normal sinus rhythm. No acute changes.",
            date.today() - timedelta(days=340),
            "Afriglobal Medicare",
        ),
        (
            "Fasting Lipid Panel",
            "Laboratory",
            "Routine metabolic screen",
            "Total cholesterol 212 mg/dL. LDL mildly elevated. Dietary intervention recommended.",
            date.today() - timedelta(days=300),
            "Afriglobal Medicare",
        ),
        (
            "Abdominal Ultrasound",
            "Imaging",
            "Evaluate liver and kidneys given metabolic risk factors",
            "Liver mildly echogenic, consistent with early fatty change. Kidneys normal.",
            date.today() - timedelta(days=180),
            "Afriglobal Medicare",
        ),
    ]
    for name, typ, reason, outcome, perf_at, location in tests:
        run(
            c,
            "INSERT INTO medical_tests (user_id, test_name, test_type, ordered_reason, outcome, performed_at, location) "
            "VALUES (:uid, :n, :t, :r, :o, :p, :loc)",
            dict(
                uid=user_id, n=name, t=typ, r=reason, o=outcome, p=perf_at, loc=location
            ),
        )
    print("✓ Medical tests seeded (3 entries)")

    appts = [
        (10, "completed", "Initial hypertension assessment"),
        (6, "completed", "3-month BP follow-up and labs review"),
        (3, "completed", "6-month metabolic review — pre-diabetes monitoring"),
    ]
    medic_clause = f"'{medic_id}'" if medic_id else "NULL"
    hosp_clause = f"'{hospital_id}'" if hospital_id else "NULL"
    for months_ago, status, reason in appts:
        scheduled = datetime.now() - timedelta(days=months_ago * 30)
        run(
            c,
            f"INSERT INTO appointments (user_id, medic_id, hospital_id, scheduled_at, department, reason, status) "
            f"VALUES (:uid, {medic_clause}, {hosp_clause}, :sched, :dept, :reason, :status)",
            dict(
                uid=user_id,
                sched=scheduled,
                dept="Afriglobal Medicare",
                reason=reason,
                status=status,
            ),
        )
    print("✓ Appointments seeded (3 completed entries)")

    run(
        c,
        "INSERT INTO health_scores (user_id, score, score_breakdown, scored_at) "
        "VALUES (:uid, :score, CAST(:breakdown AS jsonb), :scored_at)",
        dict(
            uid=user_id,
            score=6.4,
            breakdown='{"metabolic": 5.5, "cardiovascular": 6.0, "body_composition": 7.0, "lifestyle": 7.5}',
            scored_at=datetime.now() - timedelta(days=30),
        ),
    )
    print("✓ Health score seeded (6.4 / 10)")

print(f"\n✅ Done.")
print(f"   Patient : {full_name}")
print(f"   Code    : {code}")
print(f"   Provider login: admin@afriglobal.med → look up {code}")
