# Eave Health — Backend Setup

## 1. Install dependencies

```bash
cd eave-health
pip install -r requirements-clean.txt
```

## 2. Configure `.env`

The `.env` file is already set up with your Neon DB URL. Update these if needed:

```env
DATABASE_URL=
DATABASE_URL_SYNC=
JWT_SECRET=eave-health-jwt-secret-change-me-in-production
```

## 3. Initialize the database (run once)

```bash
python -m app.init_db
```

This creates all tables in your Neon DB using `createeave-updated.sql`.

## 4. Start the backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: `http://localhost:8000/docs`

## 5. Serve the frontend

Open a second terminal and serve the frontend with any static server:

```bash
cd eave-v5
python -m http.server 5500
# OR use VS Code Live Server extension
```

Then visit `http://localhost:5500/auth/login.html`

## 6. Frontend `API_BASE` config

The frontend's `shared/api.js` defaults to `http://localhost:8000`.
If your backend runs on a different host/port, edit the `BASE` constant in `api.js`.

---

## API Routes

### Auth
| Method | Path                     | Description            |
|--------|--------------------------|------------------------|
| POST   | `/api/auth/signup`       | Patient signup         |
| POST   | `/api/auth/login`        | Patient login          |
| POST   | `/api/auth/medic/signup` | Medic/provider signup  |
| POST   | `/api/auth/medic/login`  | Medic/provider login   |

### Patient (requires patient JWT)
| Method | Path                        | Description              |
|--------|-----------------------------|--------------------------|
| GET    | `/api/patient/dashboard`    | Full dashboard payload   |
| GET    | `/api/patient/profile`      | User profile             |
| PATCH  | `/api/patient/profile`      | Update profile           |
| GET    | `/api/patient/vitals`       | Vitals history           |
| POST   | `/api/patient/vitals`       | Add vitals               |
| GET    | `/api/patient/labs`         | Lab results              |
| POST   | `/api/patient/labs`         | Add lab result           |
| GET    | `/api/patient/conditions`   | Conditions               |
| POST   | `/api/patient/conditions`   | Add condition            |
| GET    | `/api/patient/medications`  | Medications              |
| POST   | `/api/patient/medications`  | Add medication           |
| GET    | `/api/patient/appointments` | Appointments             |
| GET    | `/api/patient/visits`       | Clinical visit notes     |
| GET    | `/api/patient/health-scores`| Health scores            |
| GET    | `/api/patient/predictions`  | ML risk predictions      |
| GET    | `/api/patient/tests`        | Medical tests            |
| GET    | `/api/patient/lifestyle`    | Lifestyle entries        |
| POST   | `/api/patient/lifestyle`    | Add lifestyle entry      |
| GET    | `/api/patient/family-history` | Family history         |
| POST   | `/api/patient/family-history` | Add family history     |

### Medic (requires medic JWT)
| Method | Path                              | Description              |
|--------|-----------------------------------|--------------------------|
| GET    | `/api/medic/lookup/{patient_code}`| Full patient record      |
| POST   | `/api/medic/vitals`               | Record vitals (nurse)    |
| POST   | `/api/medic/visit`                | Log clinical visit       |
| POST   | `/api/medic/appointment`          | Schedule appointment     |
| POST   | `/api/medic/test`                 | Add medical test         |
| POST   | `/api/medic/predict/{code}`       | Run ML risk prediction   |
| POST   | `/api/medic/health-score/{code}`  | Compute health score     |

### Orchestrator (existing, in-memory)
| Method | Path                    | Description              |
|--------|-------------------------|--------------------------|
| POST   | `/eave/onboard`         | Onboard patient (email)  |
| POST   | `/eave/schedule`        | Schedule appointment     |
| POST   | `/eave/post-appointment`| Post-appointment flow    |
| POST   | `/eave/run`             | Full demo pipeline       |

---

## Architecture

```
Frontend (HTML/JS)
    │
    │  fetch() + Bearer JWT
    │
    ▼
FastAPI Backend
    │
    ├── /api/auth/*      → auth_router.py   (bcrypt + JWT)
    ├── /api/patient/*   → patient_router.py (async SQLAlchemy → Neon)
    ├── /api/medic/*     → medic_router.py   (async SQLAlchemy → Neon)
    ├── /eave/*          → orchestrator.py   (email workflows via Composio)
    └── /eave/agent/*    → agent.py          (analytics + check-ins)
    │
    ▼
Neon PostgreSQL (async via asyncpg)
    │
    └── Tables: users, vitals, lab_results, conditions, medications,
                surgeries, family_history, lifestyle, risk_predictions,
                health_scores, hospitals, medics, medical_tests,
                appointments, clinical_visits
```
