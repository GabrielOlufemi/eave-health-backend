import os
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

from openai import OpenAI
from fastapi import APIRouter, HTTPException
from composio import Composio

# ── Import shared store + models from orchestrator ───────────────────────────
from app.api.orchestrator import (
    store,
    send_email,
    llm_call,
    now_iso,
    PatientProfile,
    PatientCheckIn,
)

agent_router = APIRouter()

openrouter_client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)

composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
ENTITY_ID = os.environ["COMPOSIO_ENTITY_ID"]
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


# ── ANALYTICS ENGINE ─────────────────────────────────────────────────────────


def generate_analytics(patient_id: str) -> dict:
    """
    Builds a health analytics report for a patient based on:
    - Vitals history (BP, weight, heart rate)
    - Prescription history
    - Check-in response patterns
    - Test results over time

    Returns a structured dict with trends + LLM-generated recommendations.
    """
    patient = store["patients"].get(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    history = store["medical_history"].get(patient_id, [])
    check_in = store["check_ins"].get(patient_id)
    reminders = store["reminders"].get(patient_id, [])

    # ── Build vitals trend ────────────────────────────────────────────
    vitals_trend = []
    for record in history:
        if record.vitals:
            vitals_trend.append({
                "date": record.completed_at or "unknown",
                "blood_pressure": record.vitals.blood_pressure,
                "heart_rate": record.vitals.heart_rate,
                "weight_kg": record.vitals.weight_kg,
                "temperature": record.vitals.temperature,
                "notes": record.vitals.notes,
            })

    # ── Build prescription history ────────────────────────────────────
    prescription_history = []
    for record in history:
        for rx in record.prescriptions:
            prescription_history.append({
                "date": record.completed_at or "unknown",
                "drug": rx.drug_name,
                "dosage": rx.dosage,
                "frequency": rx.frequency,
                "duration": rx.duration,
            })

    # ── Build test results history ────────────────────────────────────
    test_history = []
    for record in history:
        for test in record.tests:
            test_history.append({
                "date": test.date,
                "test": test.test_name,
                "outcome": test.outcome,
            })

    # ── Check-in engagement ───────────────────────────────────────────
    engagement = {
        "last_check_in_sent": check_in.last_check_in if check_in else None,
        "last_response": check_in.last_response if check_in else None,
        "escalated": check_in.escalated if check_in else False,
        "responded": bool(check_in and check_in.last_response),
    }

    # ── Active medications ────────────────────────────────────────────
    active_medications = [
        {"drug": r.drug_name, "dosage": r.dosage, "frequency": r.frequency}
        for r in reminders
    ]

    # ── LLM: Generate recommendations ────────────────────────────────
    system_prompt = """You are Eave's health analytics engine. You review a patient's medical history and generate:
1. A short trend summary (2-3 sentences) on vitals, medications, and test results.
2. 2-4 concrete, actionable recommendations for the patient — plain English, not clinical jargon.
3. A risk flag: "low", "moderate", or "high" based on the data.

Rules:
- Be direct and clear. Avoid hedging every sentence.
- You are NOT diagnosing. Flag concerns for discussion with a doctor.
- If data is sparse, say so and recommend a checkup.
- Tone: calm, informative, not alarming.

Respond ONLY with a JSON object:
{
  "trend_summary": "...",
  "recommendations": ["...", "...", "..."],
  "risk_flag": "low|moderate|high",
  "risk_reason": "..."
}

Return ONLY the JSON. No markdown, no explanation."""

    user_content = f"""Patient: {patient.full_name}
Age: {_calc_age(patient.dob)} years
Conditions: {', '.join(patient.medical_conditions) if patient.medical_conditions else 'None'}
Allergies: {', '.join(patient.allergies) if patient.allergies else 'None'}

Vitals History:
{json.dumps(vitals_trend, indent=2) if vitals_trend else 'No vitals recorded'}

Test Results:
{json.dumps(test_history, indent=2) if test_history else 'No tests recorded'}

Prescription History:
{json.dumps(prescription_history, indent=2) if prescription_history else 'No prescriptions recorded'}

Active Medications:
{json.dumps(active_medications, indent=2) if active_medications else 'None'}

Engagement:
- Last check-in sent: {engagement['last_check_in_sent'] or 'Never'}
- Patient responded: {engagement['responded']}
- Escalated to NOK: {engagement['escalated']}"""

    raw = llm_call(system_prompt, user_content)
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        insights = json.loads(raw)
    except Exception:
        logger.warning(f"[AGENT] Failed to parse analytics LLM response: {raw[:200]}")
        insights = {
            "trend_summary": "Insufficient data to generate a full trend summary.",
            "recommendations": ["Schedule a routine checkup with your doctor."],
            "risk_flag": "low",
            "risk_reason": "Unable to analyze — data may be incomplete.",
        }

    return {
        "patient_id": patient_id,
        "patient_name": patient.full_name,
        "generated_at": now_iso(),
        "vitals_trend": vitals_trend,
        "test_history": test_history,
        "prescription_history": prescription_history,
        "active_medications": active_medications,
        "engagement": engagement,
        "insights": insights,
    }


def _calc_age(dob: str) -> int:
    try:
        birth = datetime.strptime(dob, "%Y-%m-%d")
        return (datetime.utcnow() - birth).days // 365
    except Exception:
        return 0


# ── SEND ANALYTICS REPORT VIA EMAIL ─────────────────────────────────────────


def send_analytics_email(patient_id: str, report: dict):
    patient = store["patients"].get(patient_id)
    if not patient:
        return

    insights = report.get("insights", {})
    recommendations = insights.get("recommendations", [])
    risk_flag = insights.get("risk_flag", "low")
    risk_reason = insights.get("risk_reason", "")
    trend_summary = insights.get("trend_summary", "")

    risk_label = {
        "low": "All clear — nothing urgent to flag.",
        "moderate": "A few things worth keeping an eye on.",
        "high": "Some concerns that are worth discussing with your doctor soon.",
    }.get(risk_flag, "")

    rec_lines = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(recommendations))

    vitals = report.get("vitals_trend", [])
    latest_vitals = vitals[-1] if vitals else None
    vitals_block = ""
    if latest_vitals:
        vitals_block = f"""
Latest Vitals ({latest_vitals.get('date', 'unknown')}):
  - Blood Pressure : {latest_vitals.get('blood_pressure', 'N/A')}
  - Heart Rate     : {latest_vitals.get('heart_rate', 'N/A')} bpm
  - Weight         : {latest_vitals.get('weight_kg', 'N/A')} kg
"""

    tests = report.get("test_history", [])
    test_block = ""
    if tests:
        test_lines = "\n".join(
            f"  - {t['test']}: {t['outcome']} ({t['date']})" for t in tests[-3:]
        )
        test_block = f"\nRecent Test Results:\n{test_lines}\n"

    meds = report.get("active_medications", [])
    med_block = ""
    if meds:
        med_lines = "\n".join(
            f"  - {m['drug']} ({m['dosage']}) — {m['frequency']}" for m in meds
        )
        med_block = f"\nActive Medications:\n{med_lines}\n"

    subject = f"Your Health Summary — Eave"
    body = f"""Hi {patient.full_name.split()[0]},

Here is your latest health summary from Eave.

Overview:
{trend_summary}

Status: {risk_label}
{f"Note: {risk_reason}" if risk_flag != "low" else ""}
{vitals_block}{test_block}{med_block}
Recommendations:
{rec_lines}

This summary is based on the records we have on file. If anything looks off or you have concerns, reply to this email or bring it up at your next appointment.

— Eave"""

    send_email(patient.email, subject, body)
    logger.info(f"[AGENT] Analytics email sent to {patient.full_name}")


# ── PROACTIVE CHECK-IN SWEEP ─────────────────────────────────────────────────


def compose_check_in_email(patient: PatientProfile) -> str:
    """LLM-generated check-in body with a response link at the bottom."""
    history = store["medical_history"].get(patient.patient_id, [])
    recent_drugs = []
    if history:
        recent_drugs = [rx.drug_name for rx in history[-1].prescriptions]

    system_prompt = """You are Eave, a health companion. Write a SHORT check-in email (2-3 sentences, no sign-off).

Rules:
- Warm but not bubbly. Calm and direct.
- If they have active medications, ask how they're finding them.
- Ask ONE simple question they can answer by clicking the link below.
- No emojis. No exclamation marks. No corporate speak.
- Do NOT include a subject line, sign-off, or link — those are added separately."""

    user_content = f"""Patient: {patient.full_name}
Active medications: {', '.join(recent_drugs) if recent_drugs else 'None'}
Conditions: {', '.join(patient.medical_conditions) if patient.medical_conditions else 'None'}"""

    llm_body = llm_call(system_prompt, user_content)

    response_url = f"{BASE_URL}/eave/agent/log-response/{patient.patient_id}"

    return f"""{llm_body}

If you're doing well, just let us know by clicking below — it takes one second:
{response_url}

— Eave"""


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────


@agent_router.get("/analytics/{patient_id}")
async def get_analytics(patient_id: str):
    """
    Returns a full analytics report for the patient as JSON.
    Does NOT send an email — use /analytics/{patient_id}/send for that.
    """
    logger.info(f"[AGENT] Generating analytics for {patient_id}")
    report = generate_analytics(patient_id)
    logger.info(f"[AGENT] Analytics complete — risk: {report['insights']['risk_flag']}")
    return report


@agent_router.post("/analytics/{patient_id}/send")
async def send_analytics_report(patient_id: str):
    """
    Generates analytics and emails the report to the patient.
    """
    logger.info(f"[AGENT] Generating + sending analytics report for {patient_id}")
    report = generate_analytics(patient_id)
    send_analytics_email(patient_id, report)
    return {
        "status": "sent",
        "patient_id": patient_id,
        "risk_flag": report["insights"]["risk_flag"],
        "recommendations_count": len(report["insights"].get("recommendations", [])),
    }


@agent_router.post("/check-in-sweep")
async def check_in_sweep():
    """
    Sends check-in emails to all patients who haven't been contacted
    in the last 7 days and haven't responded to the last check-in.

    Intended to run on a daily cron schedule.
    """
    logger.info("[AGENT] ── Check-in sweep started ──")
    sent = []
    skipped = []

    for patient_id, patient in store["patients"].items():
        check_in = store["check_ins"].get(patient_id)

        # Skip if responded to last check-in (no need to ping again)
        if check_in and check_in.last_response:
            skipped.append({"patient_id": patient_id, "reason": "already_responded"})
            continue

        # Skip if checked in within the last 7 days
        if check_in and check_in.last_check_in:
            last = datetime.fromisoformat(check_in.last_check_in)
            if datetime.utcnow() - last < timedelta(days=7):
                skipped.append({"patient_id": patient_id, "reason": "checked_in_recently"})
                continue

        # Send check-in
        body = compose_check_in_email(patient)
        send_email(patient.email, "Checking in — Eave", body)

        store["check_ins"][patient_id] = PatientCheckIn(
            patient_id=patient_id,
            last_check_in=now_iso(),
            last_response=None,
            escalated=False,
        )

        sent.append(patient_id)
        logger.info(f"[AGENT] Check-in sent to {patient.full_name}")

    logger.info(f"[AGENT] Sweep complete — sent: {len(sent)}, skipped: {len(skipped)}")
    return {
        "status": "sweep_complete",
        "sent": sent,
        "skipped": skipped,
    }


@agent_router.post("/escalation-sweep")
async def escalation_sweep():
    """
    Escalates to next of kin for any patient who:
    - Was sent a check-in
    - Has NOT responded
    - Check-in was sent more than 72 hours ago
    - Has not already been escalated

    Intended to run on a daily cron schedule.
    """
    logger.info("[AGENT] ── Escalation sweep started ──")
    escalated = []

    for patient_id, check_in in store["check_ins"].items():
        if check_in.escalated:
            continue
        if check_in.last_response:
            continue
        if not check_in.last_check_in:
            continue

        last = datetime.fromisoformat(check_in.last_check_in)
        if datetime.utcnow() - last < timedelta(hours=72):
            continue

        patient = store["patients"].get(patient_id)
        if not patient or not patient.next_of_kin_email:
            continue

        subject = f"Wellness Check — {patient.full_name}"
        body = f"""Hi {patient.next_of_kin_name or 'there'},

We have been unable to reach {patient.full_name} for the past few days. This is not necessarily cause for alarm — they may simply be busy — but as their listed emergency contact, we wanted to let you know.

If you are able to, it may be worth checking in on them or encouraging them to book a routine appointment.

If everything is fine, no action is needed.

— Eave
Health companion for {patient.full_name}"""

        send_email(patient.next_of_kin_email, subject, body)
        check_in.escalated = True
        escalated.append(patient_id)
        logger.info(f"[AGENT] Escalated {patient.full_name} → {patient.next_of_kin_email}")

    logger.info(f"[AGENT] Escalation sweep complete — {len(escalated)} escalated")
    return {"status": "sweep_complete", "escalated": escalated}


@agent_router.post("/log-response/{patient_id}")
async def log_patient_response(patient_id: str):
    """
    Call this when a patient replies to a check-in email.
    Marks them as responsive so they won't be escalated.
    In production, wire this to a Gmail webhook or inbound email parser.
    """
    check_in = store["check_ins"].get(patient_id)
    if not check_in:
        raise HTTPException(status_code=404, detail="No check-in found for this patient.")

    check_in.last_response = now_iso()
    check_in.escalated = False
    logger.info(f"[AGENT] Response logged for {patient_id}")
    return {"status": "response_logged", "patient_id": patient_id}