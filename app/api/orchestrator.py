import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from openai import OpenAI
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from composio import Composio


orchestrator_router = APIRouter()

# ── Clients ──────────────────────────────────────────────────────────────────

openrouter_client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)

composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
ENTITY_ID = os.environ["COMPOSIO_ENTITY_ID"]

EAVE_EMAIL = os.environ.get("EAVE_EMAIL", "eavenotify@gmail.com")


# ── Pydantic Models ──────────────────────────────────────────────────────────

# --- Patient-side models ---


class PatientProfile(BaseModel):
    patient_id: str
    full_name: str
    email: str
    dob: str
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    allergies: list[str] = []
    medical_conditions: list[str] = []
    next_of_kin_name: Optional[str] = None
    next_of_kin_email: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    onboarded_at: Optional[str] = None


class AppointmentRequest(BaseModel):
    patient_id: str
    institution_name: str
    preferred_time: str
    preferred_date: Optional[str] = None
    reason: Optional[str] = None


class Appointment(BaseModel):
    appointment_id: str
    patient_id: str
    institution_name: str
    scheduled_date: str
    scheduled_time: str
    reason: Optional[str] = None
    status: str = "SCHEDULED"


# --- Institution-side models (mock payload) ---


class VitalsReading(BaseModel):
    patient_id: str
    nurse_id: Optional[str] = None
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None
    temperature: Optional[float] = None
    weight_kg: Optional[float] = None
    notes: Optional[str] = None
    recorded_at: Optional[str] = None


class TestResult(BaseModel):
    test_name: str
    outcome: str
    date: str


class Prescription(BaseModel):
    drug_name: str
    dosage: str
    frequency: str
    duration: Optional[str] = None
    instructions: Optional[str] = None


class PostAppointmentPayload(BaseModel):
    appointment_id: str
    patient_id: str
    doctor_name: str
    institution_name: str
    vitals: Optional[VitalsReading] = None
    prescriptions: list[Prescription] = []
    tests: list[TestResult] = []
    doctor_notes: Optional[str] = None
    completed_at: Optional[str] = None


# --- Eave agent internal models ---


class MedicationReminder(BaseModel):
    patient_id: str
    drug_name: str
    dosage: str
    frequency: str
    next_reminder_at: Optional[str] = None
    instructions: Optional[str] = None


class PatientCheckIn(BaseModel):
    patient_id: str
    last_check_in: Optional[str] = None
    last_response: Optional[str] = None
    escalated: bool = False


# ── In-Memory Store (demo only — swap for DB in production) ──────────────────

store = {
    "patients": {},
    "appointments": {},
    "reminders": {},
    "check_ins": {},
    "medical_history": {},
}


# ── Low-Level Helpers ────────────────────────────────────────────────────────


def send_email(to: str, subject: str, body: str):
    logger.info(f"Sending email to {to} | Subject: {subject}")
    composio.client.tools.execute(
        tool_slug="GMAIL_SEND_EMAIL",
        arguments={
            "recipient_email": to,
            "subject": subject,
            "body": body,
        },
        entity_id=ENTITY_ID,
    )
    logger.info(f"Email sent successfully to {to}")


async def send_email_async(to: str, subject: str, body: str):
    """Async-safe wrapper — runs the blocking composio call in a thread executor."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: send_email(to, subject, body))


def llm_call(system_prompt: str, user_content: str) -> str:
    """
    Single helper for all Gemini calls.
    Low temperature + top_p for consistent, grounded responses.
    """
    response = openrouter_client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        temperature=0.3,
        top_p=0.85,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content.strip()


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def generate_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time())}_{os.urandom(3).hex()}"


# ── Tool: ANALYZE_PRESCRIPTION ───────────────────────────────────────────────


def analyze_prescription(
    patient: PatientProfile,
    prescriptions: list[Prescription],
) -> dict:
    logger.info(
        f"Analyzing {len(prescriptions)} prescription(s) "
        f"for patient {patient.patient_id}"
    )

    system_prompt = """You are Eave's medical analysis engine. You receive a patient's profile (allergies, existing conditions) and new prescriptions from their doctor.

Your job:
1. Check each prescription against the patient's allergies. Flag ANY potential interaction — even mild ones. Be cautious, not dismissive.
2. Check each prescription against the patient's existing medical conditions for contraindications.
3. Generate a reminder schedule based on the frequency (e.g. "twice daily" = morning and evening, "every 8 hours" = 8am, 4pm, 12am).
4. Write a plain-English summary that a non-medical person would understand. Keep it clear and direct — not overly casual, not overly clinical.

IMPORTANT: You are NOT diagnosing. You are flagging potential issues for the patient to discuss with their doctor. Always recommend they consult their doctor if anything concerns them.

Respond with ONLY a JSON object:
{
  "interaction_warnings": [
    {"drug": "...", "warning": "...", "severity": "low|medium|high"}
  ],
  "reminder_schedule": [
    {"drug": "...", "dosage": "...", "times": ["8:00 AM", "8:00 PM"], "instructions": "..."}
  ],
  "plain_summary": "..."
}

Return ONLY the JSON. No markdown, no explanation."""

    user_content = f"""Patient Profile:
- Name: {patient.full_name}
- Allergies: {', '.join(patient.allergies) if patient.allergies else 'None reported'}
- Medical Conditions: {', '.join(patient.medical_conditions) if patient.medical_conditions else 'None reported'}

New Prescriptions:
{json.dumps([p.model_dump() for p in prescriptions], indent=2)}"""

    raw = llm_call(system_prompt, user_content)
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
        logger.info(
            f"Analysis complete: {len(result.get('interaction_warnings', []))} warning(s)"
        )
        return result
    except Exception:
        logger.warning(f"Failed to parse analysis, returning raw: {raw[:200]}")
        return {
            "interaction_warnings": [],
            "reminder_schedule": [],
            "plain_summary": "Your prescriptions have been recorded. Please follow your doctor's instructions.",
        }


# ── Tool: SCHEDULE_APPOINTMENT ───────────────────────────────────────────────


def schedule_appointment(request: AppointmentRequest) -> Appointment:
    logger.info(
        f"Scheduling appointment for patient {request.patient_id} "
        f"at {request.institution_name}"
    )

    system_prompt = (
        """You parse appointment time requests into structured data.

Given a preferred time (and optionally a date), return a JSON object:
{
  "date": "YYYY-MM-DD",
  "time": "HH:MM AM/PM"
}

If no date is given, assume the next available weekday from today's date.
Today's date is """
        + datetime.utcnow().strftime("%Y-%m-%d")
        + """.

Return ONLY the JSON. No explanation."""
    )

    user_content = f"Preferred time: {request.preferred_time}\nPreferred date: {request.preferred_date or 'not specified'}"

    raw = llm_call(system_prompt, user_content)
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {
            "date": request.preferred_date or datetime.utcnow().strftime("%Y-%m-%d"),
            "time": request.preferred_time,
        }

    appointment_id = generate_id("apt")

    appointment = Appointment(
        appointment_id=appointment_id,
        patient_id=request.patient_id,
        institution_name=request.institution_name,
        scheduled_date=parsed["date"],
        scheduled_time=parsed["time"],
        reason=request.reason,
        status="SCHEDULED",
    )

    store["appointments"][appointment_id] = appointment
    logger.info(
        f"Appointment {appointment_id} scheduled: "
        f"{appointment.scheduled_date} at {appointment.scheduled_time}"
    )

    return appointment


# ── Tool: CHECK_IN (proactive outreach) ──────────────────────────────────────


def compose_check_in(patient: PatientProfile) -> str:
    logger.info(f"Composing check-in for {patient.full_name}")

    history = store["medical_history"].get(patient.patient_id, [])
    recent_prescriptions = []
    if history:
        latest = history[-1]
        recent_prescriptions = [p.drug_name for p in latest.prescriptions]

    system_prompt = """You are Eave, a health companion. You're checking in on a patient — not because anything is wrong, but because consistent follow-up leads to better outcomes.

Write a SHORT email (3-4 sentences max). Rules:
- Sound like a considerate person, not a chatbot or hospital system
- Keep a calm, steady tone — warm but not bubbly
- If they have active prescriptions, ask how they're finding them
- Ask ONE simple question they can reply to
- No emojis, no exclamation marks, no over-enthusiasm
- Sign off as "— Eave"
- Do NOT include a subject line — just the body

Good tone examples:
"Hi, just checking in. How have things been going this week?"
"Wanted to see how you're doing — any changes or concerns since your last visit?"

Bad tone examples (too casual or too clinical):
"Hey!! How's it going?! Hope you're doing amazing!"
"This is a reminder to maintain your health regimen."
"""

    user_content = f"""Patient: {patient.full_name}
Active medications: {', '.join(recent_prescriptions) if recent_prescriptions else 'None currently'}
Conditions: {', '.join(patient.medical_conditions) if patient.medical_conditions else 'None noted'}"""

    return llm_call(system_prompt, user_content)


def send_check_in(patient: PatientProfile):
    body = compose_check_in(patient)
    subject = "Checking in — Eave"

    send_email(patient.email, subject, body)

    store["check_ins"][patient.patient_id] = PatientCheckIn(
        patient_id=patient.patient_id,
        last_check_in=now_iso(),
        last_response=None,
        escalated=False,
    )
    logger.info(f"Check-in sent to {patient.full_name}")


# ── Tool: ESCALATE_TO_NOK ───────────────────────────────────────────────────


def escalate_to_next_of_kin(patient: PatientProfile):
    if not patient.next_of_kin_email:
        logger.warning(
            f"Cannot escalate for {patient.patient_id} — no NOK email on file"
        )
        return

    logger.info(
        f"Escalating to NOK for patient {patient.patient_id}: "
        f"{patient.next_of_kin_name} ({patient.next_of_kin_email})"
    )

    subject = f"Wellness Check — {patient.full_name}"
    body = f"""Hi {patient.next_of_kin_name or 'there'},

We are reaching out because we have not been able to get in touch with {patient.full_name} for a few days. This is not necessarily cause for alarm — they may simply be busy — but as their listed emergency contact, we wanted to let you know.

If you are able to, it might be worth checking in on them or encouraging them to schedule a routine checkup.

If everything is fine, no action is needed — we like to err on the side of caution.

— Eave
Health companion for {patient.full_name}"""

    send_email(patient.next_of_kin_email, subject, body)

    check_in = store["check_ins"].get(patient.patient_id)
    if check_in:
        check_in.escalated = True

    logger.info(f"NOK escalation sent for {patient.patient_id}")


# ── Email Composers ──────────────────────────────────────────────────────────


def send_appointment_confirmation(patient: PatientProfile, appointment: Appointment):
    subject = f"Appointment Confirmed — {appointment.institution_name}"
    body = f"""Hi {patient.full_name},

Your appointment has been booked.

Institution: {appointment.institution_name}
Date: {appointment.scheduled_date}
Time: {appointment.scheduled_time}
{f"Reason: {appointment.reason}" if appointment.reason else ""}

If you need to reschedule, reply to this email and we will handle it.

— Eave"""

    send_email(patient.email, subject, body)


def send_prescription_summary(
    patient: PatientProfile,
    payload: PostAppointmentPayload,
    analysis: dict,
):
    rx_lines = []
    for rx in payload.prescriptions:
        line = f"  - {rx.drug_name} ({rx.dosage}) — {rx.frequency}"
        if rx.instructions:
            line += f"\n    Note: {rx.instructions}"
        rx_lines.append(line)
    rx_block = "\n".join(rx_lines) if rx_lines else "  No prescriptions this visit."

    test_lines = []
    for test in payload.tests:
        test_lines.append(f"  - {test.test_name}: {test.outcome} ({test.date})")
    test_block = "\n".join(test_lines) if test_lines else None

    warnings = analysis.get("interaction_warnings", [])
    warning_block = ""
    if warnings:
        warning_lines = []
        for w in warnings:
            severity_label = {
                "high": "[HIGH]",
                "medium": "[MEDIUM]",
                "low": "[LOW]",
            }.get(w.get("severity", "low"), "[LOW]")
            warning_lines.append(f"  {severity_label} {w['drug']}: {w['warning']}")
        warning_block = (
            "\nThings to be aware of:\n"
            + "\n".join(warning_lines)
            + "\n\nPlease discuss any concerns with your doctor."
        )

    schedule = analysis.get("reminder_schedule", [])
    schedule_lines = []
    for s in schedule:
        times = ", ".join(s.get("times", []))
        schedule_lines.append(f"  - {s['drug']} ({s['dosage']}) — {times}")
        if s.get("instructions"):
            schedule_lines.append(f"    Note: {s['instructions']}")
    schedule_block = "\n".join(schedule_lines)

    subject = f"Visit Summary — {payload.institution_name}"
    body = f"""Hi {patient.full_name},

Here is a summary of your appointment with Dr. {payload.doctor_name} at {payload.institution_name}.

Prescriptions:
{rx_block}
{warning_block}

Your medication schedule:
{schedule_block}

{f"Test Results:{chr(10)}{test_block}" if test_block else ""}

We will send you reminders based on this schedule. Reply to this email if anything changes.

Source: Appointment on {payload.completed_at or 'today'} with Dr. {payload.doctor_name} at {payload.institution_name}.

— Eave"""

    send_email(patient.email, subject, body)


async def _send_prescription_summary_async(
    patient: "PatientProfile",
    payload: "PostAppointmentPayload",
    analysis: dict,
):
    """Async-safe wrapper: builds the prescription summary email and sends it
    via run_in_executor so the blocking composio call doesn't stall the event loop."""
    rx_lines = []
    for rx in payload.prescriptions:
        line = f"  - {rx.drug_name} ({rx.dosage}) — {rx.frequency}"
        if rx.instructions:
            line += f"\n    Note: {rx.instructions}"
        rx_lines.append(line)
    rx_block = "\n".join(rx_lines) if rx_lines else "  No prescriptions this visit."

    test_lines = []
    for test in payload.tests:
        test_lines.append(f"  - {test.test_name}: {test.outcome} ({test.date})")
    test_block = "\n".join(test_lines) if test_lines else None

    warnings = analysis.get("interaction_warnings", [])
    warning_block = ""
    if warnings:
        warning_lines = []
        for w in warnings:
            severity_label = {"high": "[HIGH]", "medium": "[MEDIUM]", "low": "[LOW]"}.get(
                w.get("severity", "low"), "[LOW]"
            )
            warning_lines.append(f"  {severity_label} {w['drug']}: {w['warning']}")
        warning_block = (
            "\nThings to be aware of:\n"
            + "\n".join(warning_lines)
            + "\n\nPlease discuss any concerns with your doctor."
        )

    schedule = analysis.get("reminder_schedule", [])
    schedule_lines = []
    for s in schedule:
        times = ", ".join(s.get("times", []))
        schedule_lines.append(f"  - {s['drug']} ({s['dosage']}) — {times}")
        if s.get("instructions"):
            schedule_lines.append(f"    Note: {s['instructions']}")
    schedule_block = "\n".join(schedule_lines)

    subject = f"Visit Summary — {payload.institution_name}"
    body = (
        f"Hi {patient.full_name},\n\n"
        f"Here is a summary of your appointment with Dr. {payload.doctor_name} "
        f"at {payload.institution_name}.\n\n"
        f"Prescriptions:\n{rx_block}\n"
        f"{warning_block}\n\n"
        f"Your medication schedule:\n{schedule_block}\n\n"
        + (f"Test Results:\n{test_block}\n\n" if test_block else "")
        + f"We will send you reminders based on this schedule. Reply to this email if anything changes.\n\n"
        f"Source: Appointment on {payload.completed_at or 'today'} with Dr. {payload.doctor_name} "
        f"at {payload.institution_name}.\n\n— Eave"
    )

    await send_email_async(patient.email, subject, body)


# ── Pipeline: Onboard Patient ────────────────────────────────────────────────


@orchestrator_router.post("/onboard")
async def onboard_patient(patient: PatientProfile):
    logger.info(f"[ONBOARD] Onboarding patient: {patient.full_name}")

    patient.onboarded_at = now_iso()
    store["patients"][patient.patient_id] = patient

    subject = f"Welcome to Eave, {patient.full_name.split()[0]}"
    body = f"""Hi {patient.full_name},

Welcome to Eave. Think of us as your health companion — we work with your healthcare providers to help you stay on top of things between appointments.

Here is what we have on file for you:
  - Allergies: {', '.join(patient.allergies) if patient.allergies else 'None listed'}
  - Conditions: {', '.join(patient.medical_conditions) if patient.medical_conditions else 'None listed'}
  - Emergency contact: {patient.next_of_kin_name or 'Not provided'}

If any of this is incorrect, reply to this email and we will update it.

After each doctor's visit, we will break down your prescriptions and send you reminders when it is time to take your medication. We will also check in from time to time to see how you are doing.

— Eave"""

    send_email(patient.email, subject, body)

    logger.info(f"[ONBOARD] Patient {patient.patient_id} onboarded successfully")
    return {"status": "onboarded", "patient": patient}


# ── Pipeline: Schedule Appointment ───────────────────────────────────────────


@orchestrator_router.post("/schedule")
async def handle_appointment_request(request: AppointmentRequest):
    logger.info(
        f"[SCHEDULE] Appointment request from {request.patient_id} "
        f"at {request.institution_name}"
    )

    patient = store["patients"].get(request.patient_id)
    if not patient:
        raise HTTPException(
            status_code=404, detail="Patient not found. Please onboard first."
        )

    appointment = schedule_appointment(request)
    await send_email_async(
        patient.email,
        f"Appointment Confirmed — {appointment.institution_name}",
        f"Hi {patient.full_name},\n\nYour appointment has been booked.\n\nInstitution: {appointment.institution_name}\nDate: {appointment.scheduled_date}\nTime: {appointment.scheduled_time}\n{('Reason: ' + appointment.reason) if appointment.reason else ''}\n\nIf you need to reschedule, reply to this email.\n\n— Eave"
    )

    logger.info(f"[SCHEDULE] Appointment {appointment.appointment_id} confirmed")
    return {"status": "scheduled", "appointment": appointment}


# ── Pipeline: Post-Appointment (institution payload) ─────────────────────────


@orchestrator_router.post("/post-appointment")
async def handle_post_appointment(payload: PostAppointmentPayload):
    logger.info(
        f"[POST-APPT] ══════ Pipeline started ══════\n"
        f"  Patient: {payload.patient_id}\n"
        f"  Doctor: {payload.doctor_name}\n"
        f"  Prescriptions: {len(payload.prescriptions)}\n"
        f"  Tests: {len(payload.tests)}"
    )

    patient = store["patients"].get(payload.patient_id)
    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient not found in Eave system.",
        )

    if payload.appointment_id in store["appointments"]:
        store["appointments"][payload.appointment_id].status = "COMPLETED"

    if payload.patient_id not in store["medical_history"]:
        store["medical_history"][payload.patient_id] = []
    store["medical_history"][payload.patient_id].append(payload)

    if payload.vitals and payload.vitals.weight_kg:
        patient.weight_kg = payload.vitals.weight_kg

    # ── STAGE 1: Analyze prescriptions ───────────────────────────────
    analysis = {
        "interaction_warnings": [],
        "reminder_schedule": [],
        "plain_summary": "",
    }

    if payload.prescriptions:
        logger.info(f"[POST-APPT] Stage 1 — Analyzing prescriptions")
        analysis = analyze_prescription(patient, payload.prescriptions)
    else:
        logger.info(f"[POST-APPT] No prescriptions — skipping analysis")

    # ── STAGE 2: Email patient summary ───────────────────────────────
    logger.info(f"[POST-APPT] Stage 2 — Sending prescription summary")
    await _send_prescription_summary_async(patient, payload, analysis)

    # ── STAGE 3: Queue medication reminders ──────────────────────────
    if payload.prescriptions:
        logger.info(f"[POST-APPT] Stage 3 — Queuing reminders")
        reminders = []
        for rx in payload.prescriptions:
            reminder = MedicationReminder(
                patient_id=payload.patient_id,
                drug_name=rx.drug_name,
                dosage=rx.dosage,
                frequency=rx.frequency,
                instructions=rx.instructions,
            )
            reminders.append(reminder)

        store["reminders"][payload.patient_id] = reminders
        logger.info(f"[POST-APPT] {len(reminders)} reminder(s) queued")

    logger.info(f"[POST-APPT] ══════ Pipeline complete ══════")
    return {
        "status": "processed",
        "analysis": analysis,
        "reminders_queued": len(payload.prescriptions),
    }


# ── Pipeline: Proactive Check-In (cron-triggered) ───────────────────────────


@orchestrator_router.post("/check-in/{patient_id}")
async def trigger_check_in(patient_id: str):
    patient = store["patients"].get(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    send_check_in(patient)
    return {"status": "check_in_sent", "patient_id": patient_id}


# ── Pipeline: 72-Hour Escalation (cron-triggered) ───────────────────────────


@orchestrator_router.post("/escalation-sweep")
async def escalation_sweep():
    logger.info("[ESCALATION] Running 72-hour sweep")
    escalated = []

    for patient_id, check_in in store["check_ins"].items():
        if check_in.escalated:
            continue
        if check_in.last_response:
            continue
        if not check_in.last_check_in:
            continue

        check_in_time = datetime.fromisoformat(check_in.last_check_in)
        if datetime.utcnow() - check_in_time > timedelta(hours=72):
            patient = store["patients"].get(patient_id)
            if patient:
                escalate_to_next_of_kin(patient)
                escalated.append(patient_id)

    logger.info(f"[ESCALATION] Escalated {len(escalated)} patient(s): {escalated}")
    return {"status": "sweep_complete", "escalated": escalated}


# ── Pipeline: Send Medication Reminder ───────────────────────────────────────


@orchestrator_router.post("/send-reminders/{patient_id}")
async def send_medication_reminders(patient_id: str):
    patient = store["patients"].get(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    reminders = store["reminders"].get(patient_id, [])
    if not reminders:
        return {"status": "no_reminders", "patient_id": patient_id}

    reminder_lines = []
    for r in reminders:
        line = f"  - {r.drug_name} ({r.dosage}) — {r.frequency}"
        if r.instructions:
            line += f"\n    Note: {r.instructions}"
        reminder_lines.append(line)

    subject = "Medication Reminder"
    body = f"""Hi {patient.full_name.split()[0]},

Here is your medication schedule for today:

{chr(10).join(reminder_lines)}

If anything has changed or you have concerns, reply to this email or speak with your doctor.

— Eave"""

    send_email(patient.email, subject, body)
    logger.info(f"[REMINDER] Sent reminders to {patient.full_name}")
    return {"status": "reminders_sent", "count": len(reminders)}


# ── Utility: View patient state (for debugging/demo) ────────────────────────


@orchestrator_router.get("/patient/{patient_id}")
async def get_patient_state(patient_id: str):
    patient = store["patients"].get(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    return {
        "patient": patient,
        "appointments": [
            a for a in store["appointments"].values() if a.patient_id == patient_id
        ],
        "reminders": store["reminders"].get(patient_id, []),
        "check_in": store["check_ins"].get(patient_id),
        "medical_history": [
            p.model_dump() for p in store["medical_history"].get(patient_id, [])
        ],
    }


@orchestrator_router.get("/patients")
async def list_patients():
    return {"patients": list(store["patients"].values())}


# ── Full Demo Pipeline ───────────────────────────────────────────────────────


class DemoConfig(BaseModel):
    """
    Optional overrides for the demo run.
    If not provided, uses hardcoded Chidi Okonkwo test data.
    """

    patient_email: str = "chidi.demo@gmail.com"
    nok_email: str = "amara.demo@gmail.com"
    skip_check_in: bool = False
    skip_reminders: bool = False


@orchestrator_router.post("/run")
async def run_full_demo(config: DemoConfig = DemoConfig()):
    """
    Runs the entire Eave demo pipeline end-to-end:
    1.  Onboard patient
    2.  Schedule appointment
    3.  Post-appointment payload (with allergy trap)
    4.  Proactive check-in
    5.  Medication reminders
    6.  Analytics report (JSON + email)
    7.  Check-in sweep
    8.  Simulate patient response (log-response click)
    9.  Escalation sweep (should find nobody to escalate)
    10. Return full state

    Pass your real email in the request body to receive the emails:
    { "patient_email": "you@gmail.com", "nok_email": "backup@gmail.com" }
    """
    logger.info("[DEMO RUN] ══════ Full pipeline started ══════")
    results = {}

    # ── STEP 1: Onboard ──────────────────────────────────────────────
    logger.info("[DEMO RUN] Step 1 — Onboarding patient")
    patient = PatientProfile(
        patient_id="PAT_001",
        full_name="Chidi Okonkwo",
        email=config.patient_email,
        dob="1995-06-14",
        height_cm=178,
        weight_kg=82,
        allergies=["Penicillin", "Sulfonamides"],
        medical_conditions=["Type 2 Diabetes", "Mild Hypertension"],
        next_of_kin_name="Amara Okonkwo",
        next_of_kin_email=config.nok_email,
        next_of_kin_phone="+2348012345678",
    )

    patient.onboarded_at = now_iso()
    store["patients"][patient.patient_id] = patient

    send_email(
        patient.email,
        f"Welcome to Eave, {patient.full_name.split()[0]}",
        f"""Hi {patient.full_name},

Welcome to Eave. Think of us as your health companion — we work with your healthcare providers to help you stay on top of things between appointments.

Here is what we have on file for you:
  - Allergies: {', '.join(patient.allergies)}
  - Conditions: {', '.join(patient.medical_conditions)}
  - Emergency contact: {patient.next_of_kin_name}

If any of this is incorrect, reply to this email and we will update it.

— Eave""",
    )
    results["step_1_onboard"] = {
        "status": "onboarded",
        "patient_id": patient.patient_id,
    }
    logger.info("[DEMO RUN] Step 1 complete")

    # ── STEP 2: Schedule appointment ─────────────────────────────────
    logger.info("[DEMO RUN] Step 2 — Scheduling appointment")
    request = AppointmentRequest(
        patient_id="PAT_001",
        institution_name="Afriglobal Medicare",
        preferred_time="5PM",
        preferred_date="2026-03-28",
        reason="Routine diabetes checkup",
    )

    appointment = schedule_appointment(request)
    send_appointment_confirmation(patient, appointment)
    results["step_2_schedule"] = {
        "status": "scheduled",
        "appointment_id": appointment.appointment_id,
        "time": f"{appointment.scheduled_date} at {appointment.scheduled_time}",
    }
    logger.info("[DEMO RUN] Step 2 complete")

    # ── STEP 3: Post-appointment payload ─────────────────────────────
    logger.info("[DEMO RUN] Step 3 — Post-appointment (prescription analysis)")
    payload = PostAppointmentPayload(
        appointment_id=appointment.appointment_id,
        patient_id="PAT_001",
        doctor_name="Dr. Adeyemi",
        institution_name="Afriglobal Medicare",
        vitals=VitalsReading(
            patient_id="PAT_001",
            nurse_id="NURSE_042",
            blood_pressure="135/88",
            heart_rate=78,
            temperature=36.6,
            weight_kg=83,
            notes="Slightly elevated BP, consistent with history",
            recorded_at="2026-03-28T17:05:00",
        ),
        prescriptions=[
            Prescription(
                drug_name="Metformin",
                dosage="500mg",
                frequency="twice daily",
                duration="ongoing",
                instructions="Take with meals, morning and evening",
            ),
            Prescription(
                drug_name="Amlodipine",
                dosage="5mg",
                frequency="once daily",
                duration="ongoing",
                instructions="Take in the morning",
            ),
            Prescription(
                drug_name="Amoxicillin",
                dosage="250mg",
                frequency="three times daily",
                duration="7 days",
                instructions="Take every 8 hours, complete the full course",
            ),
        ],
        tests=[
            TestResult(
                test_name="Fasting Blood Sugar",
                outcome="142 mg/dL (elevated)",
                date="2026-03-28",
            ),
            TestResult(
                test_name="HbA1c",
                outcome="7.2% (above target)",
                date="2026-03-28",
            ),
        ],
        doctor_notes="Patient managing diabetes reasonably well. BP slightly elevated. Added Amlodipine. Short course of Amoxicillin for mild throat infection.",
        completed_at="2026-03-28T17:45:00",
    )

    store["appointments"][appointment.appointment_id].status = "COMPLETED"
    store["medical_history"]["PAT_001"] = [payload]

    if payload.vitals and payload.vitals.weight_kg:
        patient.weight_kg = payload.vitals.weight_kg

    analysis = analyze_prescription(patient, payload.prescriptions)
    send_prescription_summary(patient, payload, analysis)

    reminders = []
    for rx in payload.prescriptions:
        reminders.append(
            MedicationReminder(
                patient_id="PAT_001",
                drug_name=rx.drug_name,
                dosage=rx.dosage,
                frequency=rx.frequency,
                instructions=rx.instructions,
            )
        )
    store["reminders"]["PAT_001"] = reminders

    results["step_3_post_appointment"] = {
        "status": "processed",
        "warnings": analysis.get("interaction_warnings", []),
        "reminders_queued": len(reminders),
    }
    logger.info("[DEMO RUN] Step 3 complete")

    # ── STEP 4: Proactive check-in ───────────────────────────────────
    if not config.skip_check_in:
        logger.info("[DEMO RUN] Step 4 — Proactive check-in")
        send_check_in(patient)
        results["step_4_check_in"] = {"status": "sent"}
        logger.info("[DEMO RUN] Step 4 complete")
    else:
        results["step_4_check_in"] = {"status": "skipped"}

    # ── STEP 5: Medication reminders ─────────────────────────────────
    if not config.skip_reminders:
        logger.info("[DEMO RUN] Step 5 — Medication reminders")
        reminder_lines = []
        for r in reminders:
            line = f"  - {r.drug_name} ({r.dosage}) — {r.frequency}"
            if r.instructions:
                line += f"\n    Note: {r.instructions}"
            reminder_lines.append(line)

        send_email(
            patient.email,
            "Medication Reminder",
            f"Hi {patient.full_name.split()[0]},\n\n"
            f"Here is your medication schedule for today:\n\n"
            f"{chr(10).join(reminder_lines)}\n\n"
            f"If anything has changed or you have concerns, reply to this email or speak with your doctor.\n\n"
            f"— Eave",
        )
        results["step_5_reminders"] = {"status": "sent", "count": len(reminders)}
        logger.info("[DEMO RUN] Step 5 complete")
    else:
        results["step_5_reminders"] = {"status": "skipped"}

    # ── STEP 6: Analytics report ─────────────────────────────────────
    logger.info("[DEMO RUN] Step 6 — Generating analytics report")
    from app.api.agent import generate_analytics, send_analytics_email

    report = generate_analytics("PAT_001")
    send_analytics_email("PAT_001", report)
    results["step_6_analytics"] = {
        "status": "sent",
        "risk_flag": report["insights"]["risk_flag"],
        "recommendations_count": len(report["insights"].get("recommendations", [])),
        "risk_reason": report["insights"].get("risk_reason", ""),
    }
    logger.info(f"[DEMO RUN] Step 6 complete — risk: {report['insights']['risk_flag']}")

    # ── STEP 7: Check-in sweep ───────────────────────────────────────
    logger.info("[DEMO RUN] Step 7 — Check-in sweep")
    from app.api.agent import compose_check_in_email

    sent_sweep = []
    skipped_sweep = []

    for pid, p in store["patients"].items():
        ci = store["check_ins"].get(pid)
        if ci and ci.last_response:
            skipped_sweep.append({"patient_id": pid, "reason": "already_responded"})
            continue
        if ci and ci.last_check_in:
            last = datetime.fromisoformat(ci.last_check_in)
            if datetime.utcnow() - last < timedelta(days=7):
                skipped_sweep.append(
                    {"patient_id": pid, "reason": "checked_in_recently"}
                )
                continue
        body = compose_check_in_email(p)
        send_email(p.email, "Checking in — Eave", body)
        store["check_ins"][pid] = PatientCheckIn(
            patient_id=pid,
            last_check_in=now_iso(),
            last_response=None,
            escalated=False,
        )
        sent_sweep.append(pid)

    results["step_7_check_in_sweep"] = {
        "status": "complete",
        "sent": sent_sweep,
        "skipped": skipped_sweep,
    }
    logger.info(
        f"[DEMO RUN] Step 7 complete — sent: {len(sent_sweep)}, skipped: {len(skipped_sweep)}"
    )

    # ── STEP 8: Simulate patient response ───────────────────────────
    logger.info("[DEMO RUN] Step 8 — Simulating patient response")
    ci = store["check_ins"].get("PAT_001")
    if ci:
        ci.last_response = now_iso()
        ci.escalated = False
    results["step_8_log_response"] = {
        "status": "response_logged",
        "patient_id": "PAT_001",
    }
    logger.info("[DEMO RUN] Step 8 complete")

    # ── STEP 9: Escalation sweep (should find nobody) ────────────────
    logger.info("[DEMO RUN] Step 9 — Escalation sweep")
    escalated = []
    for pid, ci in store["check_ins"].items():
        if ci.escalated or ci.last_response or not ci.last_check_in:
            continue
        last = datetime.fromisoformat(ci.last_check_in)
        if datetime.utcnow() - last < timedelta(hours=72):
            continue
        p = store["patients"].get(pid)
        if p and p.next_of_kin_email:
            send_email(
                p.next_of_kin_email,
                f"Wellness Check — {p.full_name}",
                f"""Hi {p.next_of_kin_name or 'there'},

We have been unable to reach {p.full_name} for the past few days. This is not necessarily cause for alarm — they may simply be busy — but as their listed emergency contact, we wanted to let you know.

If you are able to, it may be worth checking in on them or encouraging them to book a routine appointment.

If everything is fine, no action is needed.

— Eave
Health companion for {p.full_name}""",
            )
            ci.escalated = True
            escalated.append(pid)

    results["step_9_escalation_sweep"] = {
        "status": "complete",
        "escalated": escalated,
        "note": (
            "Nobody escalated — patient responded in step 8"
            if not escalated
            else f"{len(escalated)} patient(s) escalated to NOK"
        ),
    }
    logger.info(f"[DEMO RUN] Step 9 complete — escalated: {len(escalated)}")

    # ── STEP 10: Final state ─────────────────────────────────────────
    final_ci = store["check_ins"].get("PAT_001")
    results["step_10_final_state"] = {
        "patient": patient.model_dump(),
        "appointments": [
            a.model_dump()
            for a in store["appointments"].values()
            if a.patient_id == "PAT_001"
        ],
        "active_reminders": len(store["reminders"].get("PAT_001", [])),
        "warnings_flagged": len(analysis.get("interaction_warnings", [])),
        "analytics_risk": report["insights"]["risk_flag"],
        "check_in_responded": bool(final_ci and final_ci.last_response),
    }

    logger.info("[DEMO RUN] ══════ Full pipeline complete ══════")
    return results