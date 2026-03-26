-- ─────────────────────────────────────────────────────────────────────────────
-- Eave Health — Complete Database Schema (createeave.sql + all additions)
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Core user table ───────────────────────────────────────────────────────────
CREATE TABLE users (
    user_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_code         VARCHAR(10) UNIQUE NOT NULL,
    full_name            VARCHAR(100) NOT NULL,
    date_of_birth        DATE NOT NULL,
    sex                  SMALLINT,                     -- 1 = Male, 2 = Female
    ethnicity            SMALLINT,                     -- mirrors RIDRETH3
    location             VARCHAR(100),
    income_poverty_ratio NUMERIC(5,2),
    next_of_kin_email    VARCHAR(150),
    blood_type           VARCHAR(5),                   -- e.g. 'O+', 'AB-'  [ADDED]
    email                VARCHAR(150) UNIQUE NOT NULL,
    password_hash        VARCHAR(255) NOT NULL,
    created_at           TIMESTAMP DEFAULT NOW()
);

-- ── Vitals / examination ──────────────────────────────────────────────────────
CREATE TABLE vitals (
    vitals_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES users(user_id) ON DELETE CASCADE,
    recorded_at  TIMESTAMP DEFAULT NOW(),
    systolic_bp  NUMERIC(5,1),
    diastolic_bp NUMERIC(5,1),
    bmi          NUMERIC(5,2),
    waist_cm     NUMERIC(5,1),
    weight_kg    NUMERIC(5,2),
    height_cm    NUMERIC(5,2),
    heart_rate   NUMERIC(5,1),                        -- bpm  [ADDED]
    temperature  NUMERIC(4,2)                         -- °C   [ADDED]
);

-- ── Lab results ───────────────────────────────────────────────────────────────
CREATE TABLE lab_results (
    lab_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID REFERENCES users(user_id) ON DELETE CASCADE,
    recorded_at       TIMESTAMP DEFAULT NOW(),
    fasting_glucose   NUMERIC(6,2),
    hba1c             NUMERIC(4,2),
    total_cholesterol NUMERIC(6,2),
    ldl_cholesterol   NUMERIC(6,2),
    triglycerides     NUMERIC(6,2)
);

-- ── Conditions / diagnoses ────────────────────────────────────────────────────
CREATE TABLE conditions (
    condition_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES users(user_id) ON DELETE CASCADE,
    condition_name VARCHAR(150) NOT NULL,
    icd_code       VARCHAR(20),
    diagnosed_at   DATE,
    is_active      BOOLEAN DEFAULT TRUE,
    notes          TEXT
);

-- ── Medications ───────────────────────────────────────────────────────────────
CREATE TABLE medications (
    medication_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(user_id) ON DELETE CASCADE,
    drug_name     VARCHAR(150) NOT NULL,
    dosage        VARCHAR(50),
    frequency     VARCHAR(50),
    started_at    DATE,
    ended_at      DATE,
    prescribed_by VARCHAR(100)
);

-- ── Surgeries ─────────────────────────────────────────────────────────────────
CREATE TABLE surgeries (
    surgery_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES users(user_id) ON DELETE CASCADE,
    surgery_name VARCHAR(150) NOT NULL,
    performed_at DATE,
    hospital     VARCHAR(150),
    notes        TEXT
);

-- ── Family history ────────────────────────────────────────────────────────────
CREATE TABLE family_history (
    entry_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES users(user_id) ON DELETE CASCADE,
    relation       VARCHAR(50),
    condition_name VARCHAR(150) NOT NULL,
    notes          TEXT
);

-- ── Lifestyle / questionnaire ─────────────────────────────────────────────────
CREATE TABLE lifestyle (
    lifestyle_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID REFERENCES users(user_id) ON DELETE CASCADE,
    recorded_at       TIMESTAMP DEFAULT NOW(),
    ever_smoked       SMALLINT,
    alcohol_use       SMALLINT,
    physically_active SMALLINT,
    diet_quality      SMALLINT,
    sleep_hours       NUMERIC(3,1)
);

-- ── ML risk predictions ───────────────────────────────────────────────────────
CREATE TABLE risk_predictions (
    prediction_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(user_id) ON DELETE CASCADE,
    predicted_at        TIMESTAMP DEFAULT NOW(),
    diabetes_risk       NUMERIC(5,4),
    hypertension_risk   NUMERIC(5,4),
    model_version       VARCHAR(20),
    age                 SMALLINT,
    sex                 SMALLINT,
    bmi                 NUMERIC(5,2),
    systolic_bp         NUMERIC(5,1),
    diastolic_bp        NUMERIC(5,1),
    fasting_glucose     NUMERIC(6,2),
    hba1c               NUMERIC(4,2),
    total_cholesterol   NUMERIC(6,2),
    waist_cm            NUMERIC(5,1),
    ever_smoked         SMALLINT,
    alcohol_use         SMALLINT,
    physically_active   SMALLINT,
    glucose_hba1c_ratio NUMERIC(8,4),
    bmi_category        SMALLINT,
    pulse_pressure      NUMERIC(5,1),
    bp_category         SMALLINT,
    age_group           SMALLINT,
    metabolic_risk      SMALLINT,
    age_x_bmi           NUMERIC(8,2),
    bmi_x_inactive      NUMERIC(8,2),
    age_x_systolic      NUMERIC(8,2)
);

-- ── Health score ──────────────────────────────────────────────────────────────
CREATE TABLE health_scores (
    score_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(user_id) ON DELETE CASCADE,
    scored_at       TIMESTAMP DEFAULT NOW(),
    score           NUMERIC(5,2),
    score_breakdown JSONB
);

-- ── Hospitals ─────────────────────────────────────────────────────────────────
CREATE TABLE hospitals (
    hospital_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(150) NOT NULL,
    location    VARCHAR(150),
    phone       VARCHAR(20),
    email       VARCHAR(150),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ── Medics (doctors/nurses) ───────────────────────────────────────────────────
CREATE TABLE medics (
    medic_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id   UUID REFERENCES hospitals(hospital_id) ON DELETE SET NULL,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    specialty     VARCHAR(100),
    room_number   VARCHAR(20),                        -- [ADDED]
    department    VARCHAR(100),                       -- [ADDED]
    created_at    TIMESTAMP DEFAULT NOW()
);

-- ── Medical tests ─────────────────────────────────────────────────────────────
CREATE TABLE medical_tests (
    test_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES users(user_id) ON DELETE CASCADE,
    test_name      VARCHAR(150) NOT NULL,
    test_type      VARCHAR(50),
    ordered_reason TEXT,
    outcome        TEXT,
    clinical_note  TEXT,
    performed_at   DATE,
    location       VARCHAR(150),
    created_at     TIMESTAMP DEFAULT NOW()
);

-- ── Appointments  [NEW TABLE] ─────────────────────────────────────────────────
-- Stores scheduled visits between patients and medics.
-- Required by the doctor record page (upcoming appointment display)
-- and the nurse intake flow.
CREATE TABLE appointments (
    appointment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES users(user_id) ON DELETE CASCADE,
    medic_id       UUID REFERENCES medics(medic_id) ON DELETE SET NULL,
    scheduled_at   TIMESTAMP NOT NULL,
    room_number    VARCHAR(20),
    department     VARCHAR(100),
    reason         TEXT,
    status         VARCHAR(20) DEFAULT 'scheduled',  -- scheduled | completed | cancelled | no_show
    created_at     TIMESTAMP DEFAULT NOW()
);

-- ── Clinical visit notes  [NEW TABLE] ─────────────────────────────────────────
-- Where the doctor's "Log Visit" form writes to.
-- Links back to the appointment that generated it.
CREATE TABLE clinical_visits (
    visit_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID REFERENCES users(user_id) ON DELETE CASCADE,
    medic_id           UUID REFERENCES medics(medic_id) ON DELETE SET NULL,
    appointment_id     UUID REFERENCES appointments(appointment_id) ON DELETE SET NULL,
    visited_at         TIMESTAMP DEFAULT NOW(),
    diagnosis_notes    TEXT,       -- Updated conditions / diagnoses field
    prescription_notes TEXT,       -- New prescriptions & orders field
    clinical_notes     TEXT        -- General visit summary & next steps
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX idx_users_patient_code       ON users(patient_code);
CREATE INDEX idx_vitals_user_id           ON vitals(user_id);
CREATE INDEX idx_labs_user_id             ON lab_results(user_id);
CREATE INDEX idx_labs_recorded_at         ON lab_results(recorded_at DESC);
CREATE INDEX idx_medications_user_id      ON medications(user_id);
CREATE INDEX idx_conditions_user_id       ON conditions(user_id);
CREATE INDEX idx_medical_tests_user_id    ON medical_tests(user_id);
CREATE INDEX idx_tests_performed_at       ON medical_tests(performed_at DESC);
CREATE INDEX idx_users_location           ON users(location);
CREATE INDEX idx_conditions_name          ON conditions(condition_name);
CREATE INDEX idx_appointments_user_id     ON appointments(user_id);
CREATE INDEX idx_appointments_medic_id    ON appointments(medic_id);
CREATE INDEX idx_appointments_scheduled   ON appointments(scheduled_at DESC);
CREATE INDEX idx_clinical_visits_user_id  ON clinical_visits(user_id);
CREATE INDEX idx_clinical_visits_medic_id ON clinical_visits(medic_id);
