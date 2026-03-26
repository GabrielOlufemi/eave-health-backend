"""
main.py — Eave Health API entry point.

Wires together:
  /api/auth/*       → signup, login (patient + medic)
  /api/patient/*    → patient CRUD (vitals, labs, conditions, etc.)
  /api/medic/*      → provider endpoints (lookup, vitals, visits, predictions)
  /eave/*           → existing orchestrator (email workflows, demo pipeline)
  /eave/agent/*     → existing agent (analytics, check-ins, escalations)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── New DB-backed routers ─────────────────────────────────────────────────────
from app.routers.auth_router import router as auth_router
from app.routers.patient_router import router as patient_router
from app.routers.medic_router import router as medic_router
from app.routers.chat_router import router as chat_router

# ── Existing orchestrator + agent (unchanged, still use in-memory store) ──────
from app.api.orchestrator import orchestrator_router
from app.api.agent import agent_router

app = FastAPI(
    title="Eave Health",
    description="Unified medical access — one companion, all your healthcare in one place.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5500",  # VS Code Live Server
        "http://127.0.0.1:5500",
        "http://localhost:8080",
        "https://eave-frontend.vercel.app",
        "https://eave-frontend-miyhgxrnn-gabriels-projects-3cafcbd3.vercel.app",
        "https://eave-health-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routers ─────────────────────────────────────────────────────────────

app.include_router(auth_router)  # /api/auth
app.include_router(patient_router)  # /api/patient
app.include_router(medic_router)  # /api/medic
app.include_router(chat_router)  # /api/chat
app.include_router(orchestrator_router, prefix="/eave", tags=["Eave Orchestrator"])
app.include_router(agent_router, prefix="/eave/agent", tags=["Eave Agent"])


@app.get("/")
async def root():
    return {"service": "Eave Health", "status": "running", "version": "0.2.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
