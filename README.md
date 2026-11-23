# HerScheme

HerScheme is a multilingual (Telugu and English) web application developed with "CODEBENDERD IDE" to help women entrepreneurs in India—specifically rural Self Help Group (SHG) members, tailors, artisans, food processors, and micro-business owners—discover, evaluate, and apply for government schemes without getting misled by middlemen or confused by complex bureaucratic rules.

---

## 1. Problem Statement & Ground Reality

In Telangana and across India, thousands of small-scale women entrepreneurs miss out on state and central welfare programs. The barriers they face on the ground include:

1. **Language and Jargon Barrier**: Official government portals are predominantly written in dense English and bureaucratic terminology, making them inaccessible to women who communicate primarily in Telugu.
2. **Fragmented and Overlapping Schemes**: State initiatives (e.g., *Indira Mahila Shakti*, *Stree Nidhi*) and Central programs (e.g., *PMEGP*, *PM Vishwakarma*, *PM Mudra*) often have overlapping target profiles and conflicting eligibility conditions. Users do not know which lane applies to them or which schemes are mutually exclusive.
3. **Exploitative Middlemen**: Fraudulent agents frequently charge ₹500 to ₹3,000 for government registrations (such as Udyam MSME registration) that the Ministry of MSME provides 100% free of charge.
4. **Privacy and Identity Theft Vulnerabilities**: Micro-entrepreneurs are routinely asked to hand over unredacted Aadhaar, PAN, voter ID, and bank passbooks to local agents, exposing them to financial fraud and misuse.

---

## 2. Core Principles & Safety Guardrails

HerScheme is engineered around four non-negotiable architectural principles:

- **Zero False Promises**: The system never uses words like "Guaranteed" or "Approved". Scheme statuses are strictly labeled as either **"Likely Eligible"** or **"Needs More Info"**.
- **In-Memory Privacy Shield**: Aadhaar, PAN, Voter ID, Ration Card, and Bank Account numbers are caught and masked in-memory before reaching any LLM prompt, database row, or server log. Raw audio from voice sessions is processed in-memory and is never stored on disk.
- **Deterministic Eligibility Evaluation**: All scheme eligibility rules, financial bands, and conflict conditions are executed by a database-backed rule engine. The LLM is used solely for natural conversation, fact extraction, and language handling—it never invents or computes eligibility rules.
- **Anti-Middleman Transparency**: Every matched scheme details free registrations (₹0), official MeeSeva statutory fees, direct government portal links, and clear 4-step application guides with WhatsApp sharing capabilities.

---

## 3. Codebenders: Project Usage & Workflow

The project was developed under the **Codebenders** umbrella. The `.codebenders/` workspace folder serves as the operational hub for design standards, orchestration, and automated verification:

- **Design System (`.codebenders/skills/flat-and-grid-design/`)**: Governs the visual presentation using the "Flat Glassmorphism & Structural Grid" design system. Key tenets include:
  - Unified glass macro-container (`bg-white/60 backdrop-blur-2xl`) over an ambient background.
  - Structural divider lines (`divide-slate-300/40`) replacing disjointed floating cards.
  - Multi-color cycling cards (`card--indigo`, `card--emerald`, `card--sky`) for scheme categories.
  - Compact typography scale and zero-margin responsive viewport.
- **Automated Verification Probes (`.codebenders/scratch/`)**: Automated measurement scripts (`measure_mic.py`, `probe_interim.py`, `measure.mjs`) used during development to verify layout stability, microphone responsiveness, and mobile viewport performance (tested across 390px mobile and 1440px desktop screens).
- **Process & Voice Diagnostics**: Runner scripts and log monitors (`voice_worker_stdout.txt`, `voice_worker_stderr.txt`) for LiveKit WebRTC agent sessions and Sarvam speech models.
- **Orchestration State (`.codebenders/state.json`)**: Tracks workflow execution phases and persistent configuration across development sprints.

---

## 4. System Architecture

HerScheme follows a decoupled architecture connecting a responsive frontend, a high-performance Python FastAPI backend, a deterministic database engine, and external AI services for speech and text inference.

```
                              +---------------------------------------+
                              |         Browser Client (Vite)         |
                              |   - Multilingual UI (Telugu / Eng)   |
                              |   - Client Privacy Banner & Regex     |
                              |   - LiveKit WebRTC Audio Client       |
                              +-------------------+-------------------+
                                                  |
                         HTTP / REST API          |  WebRTC Realtime
                                                  |  (Audio Streams)
                                                  v
                              +-------------------+-------------------+
                              |       FastAPI Backend Server          |
                              |   - Route Handlers & Health Checks    |
                              |   - In-Memory Privacy Shield Masker   |
                              |   - LiveKit Token Dispatcher          |
                              |   - Admin & Partner Auth (HMAC / JWT) |
                              +---------+-------------------+---------+
                                        |                   |
            +---------------------------+                   +--------------------------+
            v                                                                          v
+-----------------------+                                                  +-----------------------+
|  Deterministic DB     |                                                  |   AI Service Layer    |
|  (SQLite / SQLAlchemy)|                                                  |   - Groq Cloud API    |
|  - Schemes & Rules    |                                                  |     (Llama 3.3 / GPT) |
|  - Audit Log          |                                                  |   - Sarvam AI Speech  |
|  - Partner Leads      |                                                  |     (Saarika / Bulbul)|
|  - Rule Proposals     |                                                  |   - LiveKit Cloud     |
+-----------------------+                                                  +-----------------------+
```

---

## 5. Detailed Module Breakdown

### Module 1: Multilingual Accessible Home Screen
- **Telugu & English Support**: Dynamic language toggle powered by `frontend/src/i18n.js` with preferences persisted in `localStorage`.
- **Zero-Barrier Access**: No login walls, passwords, or lengthy static forms required to explore schemes.
- **Pre-Configured Demo Profiles**: 4 one-click profiles representing common user demographics (Rural SHG Pickle Maker, Warangal Tailor, Rural Artisan, Hyderabad Small Business).
- **Interactive Intake**: Includes 5 quick-search queries and a dual-mode input container supporting typed text and real-time voice conversations.

### Module 2: In-Memory Privacy Shield (`backend/app/privacy.py`)
- Automatically detects and replaces sensitive identifiers with safe tokens:
  - **Aadhaar**: Spaced or contiguous 12-digit patterns -> `[AADHAAR HIDDEN]`
  - **PAN**: 10-character alphanumeric tax IDs -> `[PAN HIDDEN]`
  - **Voter ID**: 3 letters + 7 digits -> `[VOTER ID HIDDEN]`
  - **Ration Card**: 10–12 digit sequences near contextual keywords ("ration", "రేషన్") -> `[RATION CARD HIDDEN]`
  - **Bank Account**: 9–18 digit account numbers -> `[ACCOUNT NUMBER HIDDEN]`
- Runs at both the browser boundary (`frontend/src/privacy-banner.js`) and server ingest pipeline (`backend/app/privacy_api.py`).
- Returns contextual warnings in Telugu and English. Raw numbers are never written to disk, databases, or terminal logs.

### Module 3: Conversational Fact Intake (`backend/app/followup.py`)
- Natural conversation flow that extracts five core attributes: `location`, `shg_member`, `business_status`, `loan_amount`, and `past_govt_loan`.
- Limits questions to 1 or 2 per round with an upper limit of 3 conversational rounds before concluding.
- **Failover & Key Rotation**: Uses Groq Cloud with a round-robin API key pool (`GROQ_API_KEYS`) to protect against rate limits.
- **Daily Budget Cap**: Enforces an in-memory daily limit (`CHAT_DAILY_BUDGET`) to manage cloud spend.
- **Deterministic Fallback**: If LLM services fail or network issues arise, the system immediately drops into a rule-based question flow without disrupting the user session.

### Module 4: 3-Lane Scheme Matching Engine (`backend/app/matching.py`)
- Evaluates profile facts against structured operators (`equals`, `in`, `lte`, `gte`) stored in the `scheme_rules` table.
- Categorizes matching schemes into 3 distinct lanes:
  1. **Lane 1: Telangana State Schemes**: *Indira Mahila Shakti*, *Stree Nidhi*, etc.
  2. **Lane 2: Central Loan Programs**: *PM Vishwakarma*, *PMEGP*, *PM Mudra* (Shishu/Kishore/Tarun).
  3. **Lane 3: Free Add-On Boosters**: *Udyam Registration*, *Telangana MSME Policy Incentives*.
- **Conflict Resolution ("Pick One")**: Identifies incompatible schemes (e.g., *PM Vishwakarma* vs *PMEGP*) and flags them with an orange badge explaining why the applicant must choose one.
- **Stale Verification Alerts**: Displays warning badges for schemes whose rules have not been verified against a Government Order in over 30 days.

### Module 5: Anti-Middleman Checklist (`backend/app/checklist.py`)
- Provides a transparent breakdown for each scheme:
  - **Free Documents (₹0)**: Highlights zero-cost procedures (such as Udyam registration) with warnings against paying unaccredited agents.
  - **MeeSeva Documents**: Lists statutory government fees and expected delivery timelines for income, caste, and domicile certificates.
  - **Application Portal & Guide**: Links to the official portal alongside a 4-step walkthrough.
  - **Shareable Card**: Includes a button to format and share the complete checklist directly to WhatsApp.

### Module 7: Admin Rule Governance Console (`backend/app/admin_api.py`, `frontend/admin.html`)
- Protected by administrative token authentication (`ADMIN_TOKEN`).
- Ingests Government Orders (G.O.) and compares proposed rule changes against active records.
- Provides side-by-side diff previews.
- **Audit Trail**: Approvals update the scheme's `last_verified_at` timestamp and create persistent audit entries in `audit_log`.

### Module 8: Ethical Partner & Impact Portal (`backend/app/partner_api.py`, `frontend/partners.html`)
- Supports partner banks and CSR sponsors using PBKDF2-hashed credentials and HMAC-SHA256 session tokens.
- **Opt-In Lead Flow**: Allows users viewing loan schemes to opt in for a bank callback. Contact details are saved only when the user explicitly checks the box.
- **30-Day Automated Purge**: `purge_expired_leads()` automatically removes contact information older than 30 days to enforce strict retention limits.
- **Anonymous Sponsor Impact Dashboard**: Aggregates total entrepreneurs assisted, district distribution, scheme demand, and compute cost metrics without exposing any personal user information.

### Module 9: Real-Time Voice Agent (`backend/app/voice.py`, `frontend/src/voice.js`)
- **Transport**: Real-time WebRTC audio via LiveKit Cloud.
- **Speech Pipeline**:
  - Speech-to-Text: Sarvam AI `saarika:v2.5` supporting Indian accents and Telugu.
  - Text-to-Speech: Sarvam AI `bulbul:v3` (Kavitha voice) returning natural responses under 35 words.
- **Barge-In Interruption**: Users can speak while the agent is responding; the agent stops talking and begins processing the user's speech.
- **Live Transcript Masking**: Audio chunks are transcribed, sent to the server for privacy sanitization, and rendered into the chat view in real time.
- **Fallback**: Displays an automatic advisory to use text mode if mic access fails or voice agents are unavailable.

---

## 6. Project Directory Structure

```
HerSchemes/
├── .codebenders/               # Codebenders workspace assets
│   ├── scratch/                # Automated verification scripts, logs & screenshots
│   ├── skills/                 # Design guidelines (flat-and-grid-design)
│   └── state.json              # Orchestration metadata
├── backend/
│   ├── app/
│   │   ├── admin_api.py        # Government Order ingest & rule diffs
│   │   ├── admin_auth.py       # Admin token dependency
│   │   ├── checklist.py        # Anti-middleman fee breakdowns
│   │   ├── content.py          # Quick queries loader
│   │   ├── db.py               # SQLAlchemy database session setup
│   │   ├── followup.py         # Conversational intake & fact extractor
│   │   ├── followup_api.py     # Chat follow-up endpoint
│   │   ├── impact.py           # Sponsor impact metric calculations
│   │   ├── main.py             # FastAPI entry point & CORS
│   │   ├── matching.py         # 3-lane deterministic matching engine
│   │   ├── models.py           # Database models (Schemes, Rules, Leads, Logs)
│   │   ├── partner_api.py      # Bank lead management & sponsor impact API
│   │   ├── privacy.py          # Regex & heuristic privacy maskers
│   │   ├── privacy_api.py      # Standalone privacy check endpoint
│   │   ├── schemes_repo.py     # Scheme querying & freshness checks
│   │   ├── seed.py             # Initial database seeder
│   │   ├── seed_demo.py        # Demo profiles seeder
│   │   ├── voice.py            # LiveKit & Sarvam speech integration
│   │   ├── voice_api.py        # WebRTC token minting & transcript sanitizer
│   │   └── voice_worker.py     # LiveKit dispatch voice agent worker
│   ├── seed/                   # JSON seed definitions
│   │   ├── demo_profiles.json
│   │   ├── quick_queries.json
│   │   └── schemes.json
│   ├── tests/                  # Automated pytest suite (103 tests)
│   ├── .env.example            # Environment template
│   └── requirements.txt        # Python backend dependencies
├── frontend/
│   ├── dist/                   # Production build distribution
│   ├── src/
│   │   ├── admin.js            # Admin panel logic
│   │   ├── i18n.js             # Telugu and English translation dictionary
│   │   ├── main.js             # Core user interface state machine
│   │   ├── partners.js         # Partner bank & sponsor portal
│   │   ├── portal.css          # Admin and partner portal styles
│   │   ├── privacy-banner.js   # Privacy warning component
│   │   ├── style.css           # Glassmorphic & grid stylesheets
│   │   └── voice.js            # LiveKit WebRTC client handler
│   ├── admin.html              # Admin console view
│   ├── index.html              # Primary citizen portal view
│   ├── partners.html           # Partner & sponsor view
│   ├── package.json            # Node.js dependencies
│   └── vite.config.js          # Vite build configuration
├── pyproject.toml              # Root Python project specification
└── README.md                   # Project documentation
```

---

## 7. Setup & Installation Guide

### Prerequisites
- Python 3.11 or higher
- Node.js 18 or higher (with npm)
- PowerShell or Bash terminal

### 1. Backend Setup

From the project root:

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r backend/requirements.txt
```

Configure your environment file in `backend/.env` (reference `backend/.env.example`):

```ini
# AI Models & Keys
PRIMARY_MODEL_ID=sarvam-30b
CHAT_LLM_MODEL=openai/gpt-oss-20b
CHAT_LLM_TIMEOUT=15
CHAT_DAILY_BUDGET=500
GROQ_API_KEYS=your_groq_api_key_here

# LiveKit WebRTC Settings
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
LIVEKIT_API_KEY=your_livekit_key
LIVEKIT_API_SECRET=your_livekit_secret

# Sarvam AI Speech Key
SARVAM_API_KEY=your_sarvam_key

# Admin & Partner Credentials
ADMIN_TOKEN=judge-admin-demo
PARTNER_SESSION_SECRET=judge-session-demo
```

Seed the scheme database and start the API server:

```powershell
cd backend
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

The backend API will run at `http://127.0.0.1:8000`.

### 2. Frontend Setup

From a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

The frontend application will be accessible at `http://localhost:5173`.

To build the frontend for production:

```powershell
cd frontend
npm run build
```

---

## 8. Verification & Test Suite

The test suite validates compliance with core requirements, including privacy redactors, rule-matching accuracy, administrative workflows, and lead-retention rules.

Run the test suite using pytest:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -v
```

### Test Coverage Highlights (103 Tests Passing):
- `test_privacy.py` & `test_privacy_api.py`: Tests that all formats of Aadhaar, PAN, Voter ID, Ration Card, and bank account numbers are redacted from user inputs and log targets.
- `test_matching.py`: Evaluates all 4 demo profiles against the 3-lane matching engine and checks conflict detection ("Pick One").
- `test_followup.py`: Validates fact extraction, language switching, conversation round capping, and the absence of any "Guaranteed" phrasing.
- `test_admin.py`: Tests token enforcement, rule diff generation, approval workflows, and audit logging.
- `test_partner.py`: Tests password hashing, session tokens, opt-in consent timestamps, and the 30-day automated lead purge.
- `test_stale.py`: Tests that scheme rules unverified for over 30 days are flagged with stale warning badges.
- `test_voice.py`: Validates LiveKit join token generation, Sarvam speech payloads, and in-memory transcript sanitization.

---

## 9. Evaluation & Demo Credentials

For judges and evaluators reviewing the portal interfaces:

| Portal | URL | Credentials |
| :--- | :--- | :--- |
| **Citizen App** | `http://localhost:5173/` | No login required (Open Access) |
| **Admin Console** | `http://localhost:5173/admin.html` | Demo Token: `judge-admin-demo` |
| **Partner / Sponsor** | `http://localhost:5173/partners.html` | Session Secret: `judge-session-demo` |

---

## 10. Future Roadmap

1. **WhatsApp Agent Integration**: Exposing the deterministic matching engine via a WhatsApp Business Webhook (using Twilio / Meta API) so women can query schemes directly over WhatsApp text and voice notes.
2. **Offline Kiosk Mode**: Packaging the core matching engine and Telugu audio assets into a Progressive Web App (PWA) with SQLite WASM for offline use in rural Anganwadi and Gram Panchayat centers.
3. **MeeSeva Direct Linkage**: Integrating with open MeeSeva certificate tracking APIs to provide live status updates on submitted caste and income certificates.
