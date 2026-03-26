"""
chat_router.py — Agentic chat endpoint.

The LLM gets tools it can call to perform real actions:
  - schedule_appointment  → writes to appointments table + sends confirmation email
  - get_my_vitals         → pulls latest vitals from DB
  - get_my_labs           → pulls latest lab results from DB
  - get_my_medications    → pulls active medications from DB
  - get_my_appointments   → pulls upcoming appointments from DB
  - run_risk_prediction   → runs the ML model on latest patient data
  - send_check_in_email   → triggers proactive check-in via Composio/Gmail
  - log_vitals            → patient self-reports vitals, writes to DB

The user just chats naturally. The LLM decides what to execute.
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from openai import OpenAI
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    User,
    Vital,
    LabResult,
    Medication,
    Condition,
    Appointment,
    HealthScore,
    RiskPrediction,
    Lifestyle,
    Hospital,
    ClinicalVisit,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Chat"])

client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)

# ── Tool definitions for the LLM ─────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "schedule_appointment",
            "description": "Schedule a new appointment for the patient. Use this when they ask to book, schedule, or set up an appointment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "institution_name": {
                        "type": "string",
                        "description": "Hospital or clinic name (e.g. 'Afriglobal Medicare')",
                    },
                    "date": {
                        "type": "string",
                        "description": "Appointment date in YYYY-MM-DD format. If user says 'tomorrow', compute the actual date.",
                    },
                    "time": {
                        "type": "string",
                        "description": "Appointment time (e.g. '5:00 PM', '09:30 AM')",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for the visit (e.g. 'general checkup', 'diabetes follow-up')",
                    },
                },
                "required": ["institution_name", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_vitals",
            "description": "Retrieve the patient's latest vitals (blood pressure, heart rate, weight, BMI, temperature). Use when they ask about their vitals or health numbers.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_labs",
            "description": "Retrieve the patient's latest lab results (glucose, HbA1c, cholesterol, triglycerides). Use when they ask about lab work or blood test results.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_medications",
            "description": "Retrieve the patient's active medications. Use when they ask what meds they're on, dosage, or medication schedule.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_appointments",
            "description": "Retrieve the patient's upcoming scheduled appointments. Use when they ask about upcoming visits or appointments.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_conditions",
            "description": "Retrieve the patient's active medical conditions/diagnoses. Use when they ask about their conditions or diagnoses.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_risk_prediction",
            "description": "Run the ML risk prediction model to assess the patient's diabetes and hypertension risk. Use when they ask about their risk levels or want a health assessment.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_health_score",
            "description": "Get the patient's latest health score (out of 10) with breakdown by metabolic, cardiovascular, body composition, and lifestyle pillars.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_vitals",
            "description": "Log new vitals that the patient is self-reporting. Use when they say things like 'my blood pressure is 130/85 today' or 'I weigh 80kg now'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "systolic_bp": {
                        "type": "number",
                        "description": "Systolic blood pressure (top number)",
                    },
                    "diastolic_bp": {
                        "type": "number",
                        "description": "Diastolic blood pressure (bottom number)",
                    },
                    "heart_rate": {
                        "type": "number",
                        "description": "Heart rate in bpm",
                    },
                    "weight_kg": {
                        "type": "number",
                        "description": "Weight in kilograms",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Body temperature in Celsius",
                    },
                },
                "required": [],
            },
        },
    },
]


# ── Tool execution functions ──────────────────────────────────────────────────


def _dec(v):
    """Convert Decimal to float for JSON serialization."""
    if isinstance(v, Decimal):
        return float(v)
    return v


async def _exec_schedule_appointment(args: dict, user: User, db: AsyncSession) -> str:
    """Create an appointment in the DB, matching against registered hospitals."""
    from datetime import datetime as dt
    from app.db.models import Hospital

    # Fuzzy match institution name against hospitals table
    institution_input = args.get("institution_name", "").strip()
    matched_hospital = None
    assigned_medic = None

    result = await db.execute(select(Hospital))
    hospitals = result.scalars().all()

    if hospitals:
        input_lower = institution_input.lower()
        for h in hospitals:
            if input_lower in h.name.lower() or h.name.lower() in input_lower:
                matched_hospital = h
                break

    hospital_name = matched_hospital.name if matched_hospital else institution_input

    # Auto-assign the doctor who belongs to this hospital
    if matched_hospital:
        from app.db.models import Medic

        mr = await db.execute(
            select(Medic)
            .where(Medic.hospital_id == matched_hospital.hospital_id)
            .limit(1)
        )
        assigned_medic = mr.scalar_one_or_none()

    scheduled_at = dt.fromisoformat(f"{args['date']}T{_parse_time(args['time'])}")

    appt = Appointment(
        user_id=user.user_id,
        medic_id=assigned_medic.medic_id if assigned_medic else None,
        scheduled_at=scheduled_at,
        department=hospital_name,
        reason=args.get("reason", "General appointment"),
        status="scheduled",
    )
    db.add(appt)
    await db.commit()
    await db.refresh(appt)

    # Send confirmation email — run in thread executor (composio is sync)
    email_sent = False
    try:
        hospital_detail = ""
        if matched_hospital:
            hospital_detail = f"Where: {matched_hospital.name}\nAddress: {matched_hospital.location or 'N/A'}\nPhone: {matched_hospital.phone or 'N/A'}\n"
        else:
            hospital_detail = f"Where: {institution_input}\n"

        subject = f"Appointment Confirmed — {hospital_name}"
        body = (
            f"Hi {user.full_name.split()[0]},\n\n"
            f"Your appointment has been booked.\n\n"
            + hospital_detail
            + f"Date: {args['date']}\n"
            f"Time: {args['time']}\n"
            + (f"Reason: {args.get('reason')}\n\n" if args.get("reason") else "\n")
            + "If you need to reschedule, reply to this email.\n\n— Eave"
        )

        from app.api.orchestrator import send_email_async

        await send_email_async(user.email, subject, body)
        email_sent = True
        logger.info(f"[CHAT] Appointment confirmation email sent to {user.email}")
    except Exception as e:
        logger.warning(f"[CHAT] Could not send appointment email: {e}", exc_info=True)
        email_sent = False

    return json.dumps(
        {
            "status": "scheduled",
            "appointment_id": str(appt.appointment_id),
            "where": hospital_name,
            "address": matched_hospital.location if matched_hospital else None,
            "doctor": assigned_medic.full_name if assigned_medic else None,
            "date": args["date"],
            "time": args["time"],
            "reason": args.get("reason"),
            "registered_institution": matched_hospital is not None,
            "confirmation_email_sent": email_sent,
        }
    )


def _parse_time(t: str) -> str:
    """Convert '5:00 PM' or '5PM' to '17:00:00'."""
    t = t.strip().upper()
    for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M"):
        try:
            parsed = datetime.strptime(t, fmt)
            return parsed.strftime("%H:%M:%S")
        except ValueError:
            continue
    return "09:00:00"  # fallback


async def _exec_get_vitals(user: User, db: AsyncSession) -> str:
    result = await db.execute(
        select(Vital)
        .where(Vital.user_id == user.user_id)
        .order_by(desc(Vital.recorded_at))
        .limit(3)
    )
    vitals = result.scalars().all()
    if not vitals:
        return json.dumps({"message": "No vitals recorded yet."})

    data = []
    for v in vitals:
        data.append(
            {
                "recorded_at": v.recorded_at.isoformat() if v.recorded_at else None,
                "blood_pressure": (
                    f"{_dec(v.systolic_bp)}/{_dec(v.diastolic_bp)}"
                    if v.systolic_bp
                    else None
                ),
                "heart_rate": _dec(v.heart_rate),
                "weight_kg": _dec(v.weight_kg),
                "bmi": _dec(v.bmi),
                "temperature": _dec(v.temperature),
            }
        )
    return json.dumps(data)


async def _exec_get_labs(user: User, db: AsyncSession) -> str:
    result = await db.execute(
        select(LabResult)
        .where(LabResult.user_id == user.user_id)
        .order_by(desc(LabResult.recorded_at))
        .limit(3)
    )
    labs = result.scalars().all()
    if not labs:
        return json.dumps({"message": "No lab results on file."})

    data = []
    for l in labs:
        data.append(
            {
                "recorded_at": l.recorded_at.isoformat() if l.recorded_at else None,
                "fasting_glucose": _dec(l.fasting_glucose),
                "hba1c": _dec(l.hba1c),
                "total_cholesterol": _dec(l.total_cholesterol),
                "ldl_cholesterol": _dec(l.ldl_cholesterol),
                "triglycerides": _dec(l.triglycerides),
            }
        )
    return json.dumps(data)


async def _exec_get_medications(user: User, db: AsyncSession) -> str:
    result = await db.execute(
        select(Medication).where(
            Medication.user_id == user.user_id,
            Medication.ended_at == None,
        )
    )
    meds = result.scalars().all()

    data = [
        {
            "drug_name": m.drug_name,
            "dosage": m.dosage,
            "frequency": m.frequency,
            "prescribed_by": m.prescribed_by,
            "started_at": m.started_at.isoformat() if m.started_at else None,
        }
        for m in meds
    ]

    # Also pull prescription notes written by the doctor during clinical visits
    cv_result = await db.execute(
        select(ClinicalVisit)
        .where(
            ClinicalVisit.user_id == user.user_id,
            ClinicalVisit.prescription_notes != None,
        )
        .order_by(desc(ClinicalVisit.visited_at))
        .limit(5)
    )
    visits_with_rx = cv_result.scalars().all()
    prescription_notes = [
        {
            "visited_at": v.visited_at.isoformat() if v.visited_at else None,
            "prescription_notes": v.prescription_notes,
        }
        for v in visits_with_rx
        if v.prescription_notes and v.prescription_notes.strip()
    ]

    if not data and not prescription_notes:
        return json.dumps(
            {"message": "No active medications or prescription notes on record."}
        )

    return json.dumps(
        {
            "active_medications": data,
            "prescription_notes_from_visits": prescription_notes,
        }
    )


async def _exec_get_appointments(user: User, db: AsyncSession) -> str:
    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.user_id == user.user_id,
            Appointment.status == "scheduled",
            Appointment.scheduled_at >= datetime.utcnow(),
        )
        .order_by(Appointment.scheduled_at)
        .limit(5)
    )
    appts = result.scalars().all()
    if not appts:
        return json.dumps({"message": "No upcoming appointments."})

    data = [
        {
            "scheduled_at": a.scheduled_at.isoformat() if a.scheduled_at else None,
            "department": a.department,
            "reason": a.reason,
            "status": a.status,
        }
        for a in appts
    ]
    return json.dumps(data)


async def _exec_get_conditions(user: User, db: AsyncSession) -> str:
    result = await db.execute(
        select(Condition).where(
            Condition.user_id == user.user_id,
            Condition.is_active == True,
        )
    )
    conds = result.scalars().all()
    if not conds:
        return json.dumps({"message": "No active conditions on record."})

    data = [
        {
            "condition_name": c.condition_name,
            "icd_code": c.icd_code,
            "diagnosed_at": c.diagnosed_at.isoformat() if c.diagnosed_at else None,
            "notes": c.notes,
        }
        for c in conds
    ]
    return json.dumps(data)


async def _exec_run_prediction(user: User, db: AsyncSession) -> str:
    """Pull latest data and run the ML prediction."""
    vr = await db.execute(
        select(Vital)
        .where(Vital.user_id == user.user_id)
        .order_by(desc(Vital.recorded_at))
        .limit(1)
    )
    vital = vr.scalar_one_or_none()

    lr = await db.execute(
        select(LabResult)
        .where(LabResult.user_id == user.user_id)
        .order_by(desc(LabResult.recorded_at))
        .limit(1)
    )
    lab = lr.scalar_one_or_none()

    if not vital or not lab:
        return json.dumps(
            {
                "message": "Not enough data to run prediction — need at least one vitals and one lab record."
            }
        )

    lsr = await db.execute(
        select(Lifestyle)
        .where(Lifestyle.user_id == user.user_id)
        .order_by(desc(Lifestyle.recorded_at))
        .limit(1)
    )
    lifestyle = lsr.scalar_one_or_none()

    try:
        from app.ml.predict import predict_from_patient_data

        result = predict_from_patient_data(
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

        # Store the prediction
        rp = RiskPrediction(
            user_id=user.user_id,
            diabetes_risk=result["diabetes_risk"],
            hypertension_risk=result["hypertension_risk"],
            model_version="v1.0",
        )
        db.add(rp)
        await db.commit()

        return json.dumps(
            {
                "diabetes_risk": result["diabetes_risk"],
                "diabetes_label": result["diabetes_label"],
                "hypertension_risk": result["hypertension_risk"],
                "hypertension_label": result["hypertension_label"],
            }
        )
    except Exception as e:
        logger.error(f"[CHAT] Prediction failed: {e}")
        return json.dumps({"message": f"Prediction failed: {str(e)}"})


async def _exec_get_health_score(user: User, db: AsyncSession) -> str:
    result = await db.execute(
        select(HealthScore)
        .where(HealthScore.user_id == user.user_id)
        .order_by(desc(HealthScore.scored_at))
        .limit(1)
    )
    hs = result.scalar_one_or_none()
    if not hs:
        return json.dumps(
            {
                "message": "No health score computed yet. Ask your doctor to run one at your next visit."
            }
        )

    return json.dumps(
        {
            "score": _dec(hs.score),
            "scored_at": hs.scored_at.isoformat() if hs.scored_at else None,
            "breakdown": hs.score_breakdown,
        }
    )


async def _exec_log_vitals(args: dict, user: User, db: AsyncSession) -> str:
    v = Vital(
        user_id=user.user_id,
        systolic_bp=args.get("systolic_bp"),
        diastolic_bp=args.get("diastolic_bp"),
        heart_rate=args.get("heart_rate"),
        weight_kg=args.get("weight_kg"),
        temperature=args.get("temperature"),
    )

    # Auto-compute BMI if weight is given and we have height
    if args.get("weight_kg"):
        prev = await db.execute(
            select(Vital)
            .where(Vital.user_id == user.user_id, Vital.height_cm != None)
            .order_by(desc(Vital.recorded_at))
            .limit(1)
        )
        prev_vital = prev.scalar_one_or_none()
        if prev_vital and prev_vital.height_cm:
            height_m = float(prev_vital.height_cm) / 100
            v.bmi = round(args["weight_kg"] / (height_m**2), 2)
            v.height_cm = prev_vital.height_cm

    db.add(v)
    await db.commit()

    logged = {k: v for k, v in args.items() if v is not None}
    return json.dumps({"status": "recorded", "logged": logged})


# ── Tool dispatcher ───────────────────────────────────────────────────────────


async def execute_tool(name: str, args: dict, user: User, db: AsyncSession) -> str:
    """Route a tool call to the right function."""
    logger.info(f"[CHAT] Executing tool: {name} with args: {args}")

    if name == "schedule_appointment":
        return await _exec_schedule_appointment(args, user, db)
    elif name == "get_my_vitals":
        return await _exec_get_vitals(user, db)
    elif name == "get_my_labs":
        return await _exec_get_labs(user, db)
    elif name == "get_my_medications":
        return await _exec_get_medications(user, db)
    elif name == "get_my_appointments":
        return await _exec_get_appointments(user, db)
    elif name == "get_my_conditions":
        return await _exec_get_conditions(user, db)
    elif name == "run_risk_prediction":
        return await _exec_run_prediction(user, db)
    elif name == "get_health_score":
        return await _exec_get_health_score(user, db)
    elif name == "log_vitals":
        return await _exec_log_vitals(args, user, db)
    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


# ── Chat endpoint ─────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    system: str
    messages: list[dict]


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Agentic chat — the LLM can call tools to perform real actions.
    Supports multi-turn tool use (LLM calls tool → gets result → responds).
    """

    # Inject today's date into the system prompt so the LLM can resolve "tomorrow" etc.
    today = datetime.utcnow().strftime("%Y-%m-%d")
    system_with_date = (
        body.system
        + f"\n\nToday's date is {today}. Use this to resolve relative dates like 'tomorrow', 'next week', etc."
    )

    messages = [
        {"role": "system", "content": system_with_date},
        *body.messages,
    ]

    # Allow up to 3 rounds of tool calls (in case the LLM chains actions)
    for _ in range(3):
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            temperature=0.3,
            top_p=0.85,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]

        # If the LLM wants to call tools
        if choice.finish_reason == "tool_calls" or (
            choice.message.tool_calls and len(choice.message.tool_calls) > 0
        ):
            # Add the assistant's message (with tool calls) to the conversation
            messages.append(choice.message.model_dump())

            # Execute each tool call
            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                result = await execute_tool(fn_name, fn_args, user, db)

                # Add the tool result to the conversation
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

            # Continue the loop — the LLM will see the tool results and either
            # call more tools or generate a final text response
            continue

        # No tool calls — we have a final text response
        reply = (
            choice.message.content
            or "I'm not sure how to help with that. Could you rephrase?"
        )
        return {"reply": reply}

    # Safety — if we hit the loop limit, return whatever we have
    return {
        "reply": choice.message.content
        or "I ran into an issue processing that. Could you try again?"
    }
