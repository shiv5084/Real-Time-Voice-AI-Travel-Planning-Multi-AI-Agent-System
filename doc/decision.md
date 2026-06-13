# Architecture Decision Records (ADR)

> **Project:** Real-Time Voice AI Travel Planning Multi-Agent System  
> **Author:** Shiv  
> **Date:** 2026-06-02  
> **Status:** Blueprint — decisions locked for implementation  
> **Related:** [phase-wise-implementationPlan.md](phase-wise-implementationPlan.md) · [architecture.md](architecture.md) · [eval.md](eval.md)

---

## How to Use This File

Each record documents a **tech or business decision** with enough context for future contributors to understand *why* a choice was made, not only *what* was chosen.

| Field | Description |
|-------|-------------|
| **Status** | `Accepted` (locked), `Proposed` (under review), `Superseded` (replaced by newer ADR) |
| **Context** | Problem or constraint forcing a decision |
| **Options** | Alternatives considered |
| **Decision** | What we chose |
| **Rationale** | Why this option wins |
| **Consequences** | Trade-offs, follow-up work, risks |

When a decision changes during implementation, add a new ADR (do not silently edit history). Mark the old entry `Superseded` and link to the replacement.

---

## Decision Index

| ID | Title | Phase | Status |
|----|-------|-------|--------|
| [DEC-001](#dec-001-python-runtime-version) | Python runtime version | 0 | Accepted |
| [DEC-002](#dec-002-linting-and-formatting-toolchain) | Linting & formatting toolchain | 0 | Accepted |
| [DEC-003](#dec-003-git-branch-strategy) | Git branch strategy | 7 | Accepted |
| [DEC-004](#dec-004-database-platform) | Database platform (local dev → Supabase prod) | 1 / 7 | Accepted |
| [DEC-005](#dec-005-cache-platform) | Cache platform (local Redis → Upstash prod) | 1 / 7 | Accepted |
| [DEC-006](#dec-006-row-level-security-design) | Row Level Security design | 1 | Accepted |
| [DEC-007](#dec-007-mcp-client-vs-external-mcp-servers) | MCP Client vs external MCP Servers | 2 | Accepted |
| [DEC-008](#dec-008-response-cache-ttl-per-api) | Response cache TTL per API | 2 | Accepted |
| [DEC-009](#dec-009-mcp-client-rate-limit-thresholds) | MCP Client rate limit thresholds | 2 | Accepted |
| [DEC-010](#dec-010-retry-and-backoff-strategy) | Retry & backoff strategy | 2 | Accepted |
| [DEC-011](#dec-011-dual-brain-model-assignment) | Dual-brain model assignment | 3 | Accepted |
| [DEC-012](#dec-012-per-agent-step-limits) | Per-agent step limits | 3 | Accepted |
| [DEC-013](#dec-013-parallel-worker-execution) | Parallel worker execution | 3 | Accepted |
| [DEC-014](#dec-014-langgraph-topology) | LangGraph topology | 3 | Accepted |
| [DEC-015](#dec-015-long-term-preference-store) | Long-term preference store | 4 | Accepted |
| [DEC-016](#dec-016-episodic-memory-retention) | Episodic memory retention | 4 | Accepted |
| [DEC-017](#dec-017-max-regeneration-iterations) | Max regeneration iterations | 4 | Accepted |
| [DEC-018](#dec-018-follow-up-question-priority) | Follow-up question priority | 4 | Accepted |
| [DEC-019](#dec-019-groq-whisper-api-over-local-stt) | Groq Whisper API over local STT | 5 | Accepted |
| [DEC-020](#dec-020-vad-sensitivity) | VAD sensitivity | 5 | Accepted |
| [DEC-021](#dec-021-tts-voice-selection) | TTS voice selection | 5 | Accepted |
| [DEC-022](#dec-022-voice-summary-length) | Voice summary length | 5 | Accepted |
| [DEC-033](#dec-033-free-keyless-backup-tts-engine) | Free, keyless backup TTS engine | 5 | Accepted |
| [DEC-034](#dec-034-wav-packaging-for-gemini-raw-pcm-audio) | WAV packaging for Gemini raw PCM audio | 5 | Accepted |
| [DEC-031](#dec-031-nextjs-frontend-framework) | Next.js frontend framework | 0 / 6 | Accepted |
| [DEC-032](#dec-032-local-first-infrastructure--managed-migration) | Local-first infrastructure & managed migration | 0–7 | Accepted |
| [DEC-023](#dec-023-frontend-styling-superseded) | ~~Frontend CSS~~ (superseded by DEC-031) | 6 | Superseded |
| [DEC-024](#dec-024-pdf-generation-library) | PDF generation library | 6 | Accepted |
| [DEC-025](#dec-025-default-ui-theme) | Default UI theme | 6 | Accepted |
| [DEC-026](#dec-026-budget-visualization) | Budget visualization | 6 | Accepted |
| [DEC-027](#dec-027-production-hosting-provider) | Production hosting provider | 7 | Proposed |
| [DEC-028](#dec-028-nextjs-deployment-vercel) | Next.js deployment (Vercel) | 7 | Proposed |
| [DEC-029](#dec-029-observability-stack) | Observability stack | 7 | Proposed |
| [DEC-030](#dec-030-production-scaling-strategy) | Production scaling strategy | 7 | Proposed |

---

## Phase 0 — Scaffolding & DevOps

### DEC-001: Python Runtime Version

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 0 |
| **Date** | 2026-06-02 |

**Context:** Backend is FastAPI + LangGraph with heavy async I/O (agents, MCP clients, SSE). Runtime choice affects library compatibility, performance, and team onboarding.

**Options:**
1. Python 3.10 — widest legacy support
2. Python 3.11+ — improved asyncio, faster CPython, better typing
3. Python 3.12 — newest features, some ML/voice libs lag on wheels

**Decision:** Python **3.11+** (pin minor in `requirements.txt` / Docker).

**Rationale:** 3.11 delivers measurable asyncio and startup gains for multi-agent pipelines; LangChain/LangGraph/FastAPI all support 3.11 well. 3.12 adds risk for some scientific wheels (webrtcvad) without benefit for v1.

**Consequences:** Developers must use 3.11+ locally; CI matrix is single version (simpler). Upgrade path to 3.12 documented for Phase 7 if dependency matrix stabilizes.

---

### DEC-002: Linting and Formatting Toolchain

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 0 |
| **Date** | 2026-06-02 |

**Context:** Multi-agent codebase needs consistent style and fast CI feedback.

**Options:**
1. flake8 + isort + black
2. **ruff** (lint) + **black** (format) + **mypy** (types)
3. ruff-only (format + lint)

**Decision:** **ruff** + **black** + **mypy** in GitHub Actions.

**Rationale:** Ruff replaces flake8/isort with one fast tool; black remains the formatting standard the team knows; mypy catches Pydantic/LangGraph typing issues early.

**Consequences:** `pyproject.toml` or `ruff.toml` required; **CI runs in Phase 7** (not Phase 0).

---

### DEC-003: Git Branch Strategy

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | **7** (final stage — repo init and push with complete project) |
| **Date** | 2026-06-02 |

**Context:** Solo/small-team project with phased delivery needs safe integration without blocking experiments.

**Options:**
1. Trunk-only (`main` only)
2. GitFlow (`main` + `develop` + release branches)
3. **GitHub Flow variant:** `main` (protected) + `dev` + `feature/*`

**Decision:** Protected **`main`**, integration **`dev`**, short-lived **`feature/*`** branches; PRs into `dev`, release PR `dev` → `main`.

**Rationale:** Lighter than GitFlow; `dev` holds phase-complete work while `main` stays deployable for demos.

**Consequences:** Branch protection on `main`; tag releases at end of Phase 7. **No Git init in Phase 0** — local development proceeds without remote until final stage.

---

### DEC-031: Next.js Frontend Framework

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 0 (skeleton) / 6 (full UI) |
| **Date** | 2026-06-02 |

**Context:** Need a maintainable, production-grade frontend with routing, auth integration, and SSR/SSG options for travel UI.

**Options:**
1. Vanilla HTML/CSS/JS — no build tooling, harder to scale components
2. **Next.js 14+ App Router** — TypeScript, Tailwind, Supabase auth client, Vercel deploy
3. React SPA (Vite) — no file-based routing out of the box

**Decision:** **Next.js 14+** with App Router, TypeScript, Tailwind CSS; Supabase JS client for auth; API calls via `src/lib/api.ts` to FastAPI.

**Rationale:** Aligns with modern React ecosystem; first-class Vercel deployment; component model fits voice/chat/planner UIs.

**Consequences:** `package.json` in `frontend/`; CI runs `npm run build`; Phase 6 owns all routes under `src/app/`.

---

### DEC-032: Local-First Infrastructure & Managed Migration

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 0–6 (local) · **7 (migration)** |
| **Date** | 2026-06-02 |

**Context:** Team needs fast offline-friendly development without cloud DB costs, but production targets Supabase + Upstash per product architecture.

**Options:**
1. Managed services only from day one — no local DB
2. **Local Postgres + Redis in Docker for dev; migrate to managed in Phase 7**
3. Local forever — no managed migration

**Decision:**
- **Phases 0–6:** `docker-compose.yml` includes `postgres` + `redis`; `APP_ENV=local`; `DATABASE_URL` + `REDIS_URL`
- **Phase 7:** Run `scripts/migrate_to_managed.py`; switch to `APP_ENV=production`; deploy with `docker-compose.prod.yml` (no DB containers)
- **Keep** `docker-compose.yml` for ongoing local development after launch

**Rationale:** User-approved strategy ([prompt.md](prompt.md)); reduces friction during feature phases; single controlled cutover before Git/CI/production.

**Consequences:** `config.py` must support both connection profiles; RLS enforced on Supabase after migration; Phase 7 eval includes pre- and post-migration golden dataset runs.

---

## Phase 1 — Data Layer & Authentication

### DEC-004: Database Platform

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 1 / 7A |
| **Date** | 2026-06-02 |
| **Updated:** 2026-06-08 |

**Context:** Need PostgreSQL for trips, itineraries, episodic memory, audit logs, plus built-in auth for v1 velocity.

**Options:**
1. Self-hosted PostgreSQL (Docker) — full control, more ops
2. **Supabase** (managed PostgreSQL + Auth + RLS)
3. PlanetScale / other — MySQL, weaker fit for JSON episodic fields

**Decision:** **Local PostgreSQL** (Docker) for Phases 0–6 development and testing. **Supabase PostgreSQL** for production after Phase 7 migration. **Supabase Auth** used throughout (OAuth/JWT) — auth is cloud-based even when data is local.

**Rationale:** Same schema DDL in `supabase/migrations/` applies to both local and Supabase; migration script promotes data in Phase 7. RLS policies defined in migrations, **enabled on Supabase** at cutover.

**Consequences:** `DATABASE_URL` for local; `SUPABASE_URL` + service key for production DB access; `seed_db.py` targets local Postgres until migration.

**Implementation Status:** ✅ **COMPLETED** (Phase 7A)
- Migration script `scripts/migrate_to_managed.py` completed successfully
- Supabase tables + RLS active; 3 profiles + 2 trips persisted
- Verified via `verify_supabase.py`

---

### DEC-005: Cache Platform

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 1 / 7A |
| **Date** | 2026-06-02 |
| **Updated:** 2026-06-08 |

**Context:** Session state, MCP response cache, and rate-limit counters need low-latency Redis.

**Options:**
1. Self-hosted Redis in Docker
2. **Upstash Redis** (serverless, HTTP/Redis protocol)
3. In-memory only — breaks multi-instance scaling

**Decision:** **Local Redis** in `docker-compose.yml` for Phases 0–6 (`REDIS_URL=redis://redis:6379`). **Upstash Redis** for production after Phase 7 (`UPSTASH_REDIS_URL` + token). No data migration needed for Redis (cache cold start acceptable).

**Rationale:** Identical Redis API; MCP middleware and session code unchanged — only connection string switches via `APP_ENV`.

**Consequences:** Phase 7 task: create Upstash instance, update `.env.production`, smoke-test cache layers.

**Implementation Status:** ✅ **COMPLETED** (Phase 7A)
- Upstash Redis session + MCP cache verified
- PING/SET/GET/TTL/DELETE operations verified via `verify_upstash.py`
- Added `redis_url` / `redis_token` properties to `SessionManager` for Upstash support

---

### DEC-006: Row Level Security Design

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 1 |
| **Date** | 2026-06-02 |

**Context:** User trips and preferences are sensitive; defense must not rely on application bugs alone.

**Options:**
1. Application-only filtering (`WHERE user_id = ?`)
2. **RLS on all user-owned tables** + service role for admin scripts only
3. Separate database per user — impractical

**Decision:** Enable **RLS** on `profiles`, `trips`, `itineraries`, `episodic_memory`, `chat_messages`; policies: `auth.uid() = user_id`. `audit_log` writable by service role, readable by owner trip linkage.

**Rationale:** Aligns with Security Architecture §9; satisfies “User Trust” design principle.

**Consequences:** Backend must pass user JWT to Supabase client for user-scoped queries; seed scripts use service role key with care.

---

## Phase 2 — MCP Client Middleware

### DEC-007: MCP Client vs External MCP Servers

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 2 |
| **Date** | 2026-06-02 |

**Context:** External travel APIs must be tool-accessible to agents; MCP standardizes tool contracts.

**Options:**
1. Implement MCP Servers **in this repo**
2. **MCP Clients in this repo** → **External MCP Servers** (separate project)
3. Direct REST wrappers per API — no MCP

**Decision:** **MCP Clients only** in this project; MCP Servers hosted externally. No agent calls external APIs without passing through `BaseMCPClient` middleware.

**Rationale:** User directive in [prompt.md](prompt.md); separates API credential management; enforces schema validation, retry, rate limit, cache, audit before any outbound call.

**Consequences:** Dependency on external MCP server availability and schema contracts; version MCP schemas in `mcp_clients/schemas/`.

---

### DEC-008: Response Cache TTL per API

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 2 |
| **Date** | 2026-06-02 |

**Context:** Reduce latency, cost, and external quota usage while keeping data fresh enough for travel planning.

**Options:**
1. Single global TTL (e.g. 1 hour)
2. **Per-API TTL** tuned to data volatility
3. No caching — unacceptable cost/latency at scale

**Decision:** Redis cache TTLs per [architecture.md §12.3](architecture.md):

| Cache target | TTL |
|--------------|-----|
| Flight search | 1 hour |
| Hotel search | 1 hour |
| Attractions (Tavily) | 24 hours |
| Geocoding (Nominatim) | 7 days |
| Routes (GraphHopper/OSRM) | 24 hours |
| Gmail send | No cache (idempotent send only) |

**Rationale:** Matches data change frequency; geocoding longest TTL saves Nominatim load.

**Consequences:** Cache keys must include normalized arguments (origin, destination, dates); stale flight prices acceptable for planning draft, not for booking.

---

### DEC-009: MCP Client Rate Limit Thresholds

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 2 |
| **Date** | 2026-06-02 |

**Context:** Protect external MCP server quotas and avoid cascading failures when many users plan trips concurrently.

**Options:**
1. No client-side limits — rely on external server only
2. **Per-MCP-server token bucket** in Redis + global per-user API limit at FastAPI layer
3. Hard global cap only

**Decision:**
- **FastAPI perimeter:** 10 trip-plan requests per user per hour (architecture §9.1).
- **MCP Client layer (per server, sliding window, Redis):** conservative defaults, configurable via env:

| MCP Client | Default limit | Window |
|------------|---------------|--------|
| AviationStack | 30 calls | 1 min |
| Tavily | 20 calls | 1 min |
| GraphHopper/OSRM | 40 calls | 1 min |
| Nominatim | 10 calls | 1 min |
| Gmail | 5 sends | 1 hour |

**Rationale:** Nominatim is strictest public API; flight/hotel bursts happen during parallel worker phase; Gmail is low volume.

**Consequences:** Tune limits after Phase 7 load tests; expose `MCP_RATE_LIMIT_*` env vars; return 429 with retry-after to agents.

---

### DEC-010: Retry and Backoff Strategy

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 2 |
| **Date** | 2026-06-02 |

**Context:** Transient network and 5xx errors are common for travel APIs; blind retries waste quota.

**Options:**
1. Fixed 3 retries, no backoff
2. **Exponential backoff with jitter**, max 3 attempts, retry only transient errors
3. Unlimited retries — dangerous

**Decision:** Max **3 attempts**; backoff `min(2^attempt + random(0,1), 8)` seconds; retry on timeout, 429, 502–504; **no retry** on 4xx (except 429), schema validation failures, or auth errors.

**Rationale:** Matches Error Handling Strategy §10.2; jitter prevents thundering herd.

**Consequences:** Total tool call timeout budget must fit latency target (< 10s p95 end-to-end); log each retry in `audit_log`.

---

## Phase 3 — Core Agent Pipeline

### DEC-011: Dual-Brain Model Assignment

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 3 |
| **Date** | 2026-06-02 |

**Context:** Product requires < 10s end-to-end while Budget and Validator need arithmetic and compliance rigor.

**Options:**
1. Single model (Gemini only) — slower, costlier
2. Single model (Groq only) — weak budget/validation
3. **Dual-brain:** Groq for speed agents, Gemini for rigor agents

**Decision:**

| Agent | Model |
|-------|-------|
| Planner, Flight, Hotel, Attraction, Transport, Composer | **Groq** |
| Budget, Validator | **Gemini** |

**Rationale:** Documented in [architecture.md §5](architecture.md) Model Assignment; satisfies Cost Efficiency + User Trust principles.

**Consequences:** Two API keys, two failure modes; fallback policy in Phase 7 if one provider is down.

---

### DEC-012: Per-Agent Step Limits

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 3 |
| **Date** | 2026-06-02 |

**Context:** Unbounded agent loops blow latency and token cost.

**Options:**
1. Global 10 steps for all agents
2. **Per-agent limits** from architecture component diagram
3. No limits — unacceptable

**Decision:** Planner **5**, parallel workers **3** each, Budget **2**, Composer **3**, Validator **2**.

**Rationale:** Workers need fewer steps (single tool focus); Planner needs more for Q&A and delegation; Validator is critique-only.

**Consequences:** Hard-stop in `BaseAgent` when limit reached; return partial state + flag for Validator.

---

### DEC-013: Parallel Worker Execution

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 3 |
| **Date** | 2026-06-02 |

**Context:** Four workers are independent after Planner delegation; sequential execution violates latency budget.

**Options:**
1. Sequential worker calls
2. **`asyncio.gather`** inside a single LangGraph node
3. **LangGraph `Send` API / fan-out** native parallel branches

**Decision:** **LangGraph fan-out/fan-in** for four workers; implement node bodies with `asyncio.gather` for I/O-bound MCP calls.

**Rationale:** Fan-out visible in graph diagrams and traces; gather keeps MCP concurrency efficient.

**Consequences:** Integration test asserts wall-clock < 1.5× slowest worker; shared state writes must be merge-safe.

---

### DEC-014: LangGraph Topology

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 3 |
| **Date** | 2026-06-02 |

**Context:** Pipeline has parallel segment, sequential synthesis, and conditional regeneration (Phase 4).

**Options:**
1. Fixed linear graph only — cannot regen selectively
2. **Conditional edges** after Validator (approve vs regen vs escalate)
3. Fully dynamic graph per request — over-engineered

**Decision:** Fixed topology: `Planner → [Flight|Hotel|Attraction|Transport] → Budget → Composer → Validator` with **conditional edge** from Validator back to Planner (regen) or END (approve/warn).

**Rationale:** Matches Manager–Worker + Sequential Synthesis pattern in problem statement.

**Consequences:** Phase 4 adds regen edge and selective worker re-entry without redrawing entire graph.

---

## Phase 4 — Memory & Self-Correction

### DEC-015: Long-Term Preference Store

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 4 |
| **Date** | 2026-06-02 |

**Context:** Cross-trip preferences (food, style, transport) should not require custom ML infra in v1.

**Options:**
1. Custom `preferences` JSONB only in PostgreSQL
2. **Mem0** for semantic preference memory
3. Both Mem0 + full duplicate in Postgres

**Decision:** **Mem0** as source of truth for long-term preferences; PostgreSQL `profiles` holds editable overrides and display fields.

**Rationale:** Architecture §4 memory layer; Mem0 optimized for preference retrieval; episodic stays in Postgres (DEC-016).

**Consequences:** Mem0 API key required; graceful degradation if Mem0 unavailable (use profile JSON only).

---

### DEC-016: Episodic Memory Retention

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 4 |
| **Date** | 2026-06-02 |

**Context:** Past trip learnings help repeat destinations but unbounded storage raises privacy and cost concerns.

**Options:**
1. Forever retention
2. **1-year rolling retention**
3. 30-day retention — too short for annual travelers

**Decision:** **1-year retention** on `episodic_memory`; scheduled purge job (monthly).

**Rationale:** Aligns with architecture memory layer; balances personalization and GDPR-style minimization.

**Consequences:** Purge script in `scripts/`; export on user delete request within 24h (Ethical AI §14).

---

### DEC-017: Max Regeneration Iterations

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 4 |
| **Date** | 2026-06-02 |

**Context:** Validator may reject plans; infinite loops harm UX and cost.

**Options:**
1. Unlimited regen until pass
2. **Max 3** regen cycles
3. Max 1 — too strict for complex trips

**Decision:** **`regeneration_count` max 3**; after max, deliver plan with **warnings** and human override in UI.

**Rationale:** Product strategy self-correcting loop; architecture error handling; target mean regen < 1.5.

**Consequences:** State field `regeneration_count`; Validator must emit structured feedback for selective re-run (DEC-014 edge).

---

### DEC-018: Follow-Up Question Priority

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 4 |
| **Date** | 2026-06-02 |

**Context:** Vague voice/text requests need clarification without interrogating users who already have profiles.

**Options:**
1. Ask all fields upfront
2. **Priority queue:** dates → budget → travelers → destination (if missing)
3. Random order — poor UX

**Decision:** Ask **one question at a time**, max **2–3** questions; order: **dates → budget → travelers**; skip fields already in Mem0/profile unless user overrides.

**Rationale:** Voice-first UX; Golden Dataset #7 needs discovery without form fatigue.

**Consequences:** Planner prompt encodes priority; unit tests for skip logic when prefs exist.

---

## Phase 5 — Voice Pipeline

### DEC-019: Groq Whisper API over Local STT

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 5 |
| **Date** | 2026-06-03 |

**Context:** STT must hit ≥90% accuracy on travel phrases while keeping voice path latency low **and memory overhead minimal**. The original plan used `faster-whisper` (local inference), which required 1–4 GB VRAM/RAM, CUDA driver setup, and a large Docker image.

**Options:**
1. `faster-whisper` (local) — high memory, GPU/CUDA dependency, large Docker image
2. **Groq Whisper API (cloud)** — zero local memory, reuses existing `GROQ_API_KEY`, equivalent accuracy
3. OpenAI Whisper API — same concept but separate key, higher cost

**Decision:** **Groq Whisper API** using model `whisper-large-v3-turbo`; configurable via `GROQ_WHISPER_MODEL` env var.

**Rationale:** Eliminates GPU memory requirement and CUDA dependency entirely. Reuses the `GROQ_API_KEY` already required for LLM agents — no new credentials needed. `whisper-large-v3-turbo` on Groq delivers ~300 ms median latency with accuracy equivalent to `whisper-large-v3`. Free tier covers 7200 seconds/day which is ample for development and demo usage.

**Consequences:** STT now depends on network availability (as do all other LLM/API calls). `faster-whisper` removed from `requirements.txt`; Docker image size reduced. Model variant can be changed via `GROQ_WHISPER_MODEL` without code changes.

---

### DEC-020: VAD Sensitivity

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 5 |
| **Date** | 2026-06-02 |

**Context:** WebRTC VAD controls when STT runs; too aggressive wastes API calls, too loose captures noise.

**Options:**
1. Default WebRTC mode 3 only
2. **Mode 2** with 300ms end-of-speech padding
3. Manual push-to-talk only

**Decision:** WebRTC VAD **mode 2** (aggressive balance); **300ms** trailing silence to end utterance; max utterance **60 sec** (security input limit).

**Rationale:** Architecture input limits; reduces false triggers vs mode 0–1.

**Consequences:** Tunable via `VAD_MODE` env; frontend shows “listening” indicator tied to VAD events.

---

### DEC-021: TTS Voice Selection

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 5 |
| **Date** | 2026-06-02 |

**Context:** Voice summary is opt-in brand touchpoint; should sound professional and neutral.

**Options:**
1. Platform default voice
2. **ElevenLabs preset** — configurable `ELEVENLABS_VOICE_ID`
3. Clone custom voice — legal/ethical overhead for v1

**Decision:** ElevenLabs **`cgSgspJ2msm6clMCkdW9`** (Jessica) as default; override via env for localization later.

**Rationale:** Clear, neutral English; widely used for demos; avoids voice cloning ethics issues in v1.

**Consequences:** ElevenLabs API cost per summary; fallback to text-only if TTS fails.

---

### DEC-022: Voice Summary Length

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 5 |
| **Date** | 2026-06-02 |

**Context:** Users want highlights hands-free, not full itinerary read aloud.

**Options:**
1. Full itinerary TTS — too long
2. **30–45 second** condensed summary
3. 10-second clip — insufficient detail

**Decision:** Composer/Planner produces **≤ 120 words** summary script targeting **30–45 seconds** audio; no day-by-day listing in TTS.

**Rationale:** Problem statement voice output requirement; reduces TTS cost.

**Consequences:** Prompt template for summary; manual QA in Phase 5 eval 5.5.

---

### DEC-033: Free, Keyless Backup TTS Engine

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 5 |
| **Date** | 2026-06-12 |

**Context:** ElevenLabs and Gemini TTS are dependent on valid API keys and usage quotas. ElevenLabs free tier may disable access due to unusual activity (e.g. proxy/VPN detection), and Gemini's free-tier TTS model is limited to 10 requests per day per project. If keys are missing, blocked, or exhausted, Text-to-Speech fails, causing silence in the frontend.

**Options:**
1. Log warning and fail silently with text-only mode
2. Require users to supply their own paid ElevenLabs/Gemini keys
3. **Integrate Google Translate TTS** as a free, keyless, zero-config tertiary fallback

**Decision:** Integrate **Google Translate TTS** (via `GoogleTranslateTTS` class) as the third tier in `FallbackTTS`.

**Rationale:** Google Translate TTS requires no API keys, has high rate limits, and is highly reliable. Splitting text into segments (< 200 characters) and concatenating the returned MP3 bytes guarantees that the voice summary is always generated and audible during local development and production.

**Consequences:** Voice summaries will always fall back to standard Google TTS when cloud keys are unavailable. Concatenated MP3 segments play back seamlessly.

---

### DEC-034: WAV Packaging for Gemini Raw PCM Audio

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 5 |
| **Date** | 2026-06-12 |

**Context:** Gemini Native TTS API returns raw, headerless 16-bit PCM audio (`pcm_24000`). Standard HTML5 `<audio>` elements do not natively support decoding or playing headerless PCM audio (`audio/L16;rate=24000`), resulting in playback errors in the browser.

**Options:**
1. Decode raw PCM using Web Audio API on the frontend (requires complex buffer management)
2. **Pre-wrap raw PCM in a standard WAV container** on the backend and serve as `audio/wav`
3. Avoid using Gemini TTS altogether

**Decision:** Wrap Gemini's raw PCM audio bytes with a standard **44-byte WAV header** on the backend and set `audio_format = "wav"` / MIME type `audio/wav`.

**Rationale:** Wrapping the PCM bytes in a WAV header makes it a standard, containerized WAV file. Standard browsers and the frontend `<audio>` elements can decode and play the WAV audio natively without any custom frontend code or decoding libraries.

**Consequences:** Frontend audio players play Gemini fallback summaries perfectly out-of-the-box. The backend voice router maps `"wav"` to the correct `"audio/wav"` MIME type.

---

## Phase 6 — Frontend & Output

### DEC-023: Frontend Styling (Superseded)

| | |
|---|---|
| **Status** | **Superseded** by [DEC-031](#dec-031-nextjs-frontend-framework) |
| **Phase** | 6 |

**Decision (historical):** Vanilla CSS files — replaced by **Tailwind CSS** via Next.js.

---

### DEC-024: PDF Generation Library

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 6 |
| **Date** | 2026-06-02 |

**Context:** Branded downloadable trip report with tables and day sections.

**Options:**
1. **ReportLab** — programmatic PDF, precise layout
2. WeasyPrint — HTML → PDF, heavier system deps
3. Client-side pdf.js — inconsistent branding

**Decision:** **ReportLab** for `services/pdf.py`.

**Rationale:** Pure Python, Docker-friendly, good for structured itinerary tables; WeasyPrint adds Cairo/GTK ops burden on Windows CI.

**Consequences:** PDF templates coded in Python; iterate layout in Phase 6 eval 6.6.

---

### DEC-025: Default UI Theme

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 6 |
| **Date** | 2026-06-02 |

**Context:** Product positioning is modern, premium travel assistant.

**Options:**
1. Light mode default
2. **Dark mode default** with optional light toggle (Phase 6+)
3. System-only — no brand identity

**Decision:** **Dark mode default**; tokens for surfaces `#0f1419`, accent travel-teal; light mode deferred post-v1.

**Rationale:** AI/travel products skew dark premium aesthetic in strategy doc; reduces eye strain for planning sessions.

**Consequences:** All components built with dark tokens first; contrast checks for WCAG AA on primary text.

---

### DEC-026: Budget Visualization

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 6 |
| **Date** | 2026-06-02 |

**Context:** Itinerary view needs interactive budget breakdown in Next.js.

**Options:**
1. CSS-only bars
2. **Recharts** (React chart library)
3. Chart.js via CDN — poor fit for React components

**Decision:** **Recharts** in `BudgetChart.tsx`.

**Rationale:** Native React components; works with Next.js client components; hover tooltips for category breakdown.

**Consequences:** Add `recharts` to `frontend/package.json`; chart renders as client component.

---

## Phase 7 — Production Readiness

> Phase 7 ADRs are **Proposed** until load testing and deployment confirm constraints. Update status to `Accepted` at Phase 7 sign-off.

### DEC-027: Production Hosting Provider

| | |
|---|---|
| **Status** | Accepted (Partial) |
| **Phase** | 7 |
| **Date** | 2026-06-02 |
| **Updated:** 2026-06-08 |

**Context:** FastAPI + Redis + voice workloads need simple deploy with Docker and reasonable cold start.

**Options:**
1. **Railway** — Docker-native, simple env secrets
2. Render — similar, slightly different pricing
3. AWS ECS — maximum control, highest ops

**Decision:** **Railway** for backend API; **Vercel** for Next.js frontend.

**Rationale:** Vercel is native to Next.js (preview deploys, edge); Railway handles Python/FastAPI containers.

**Consequences:** `NEXT_PUBLIC_API_URL` points to Railway backend; CORS allows Vercel origin.

**Implementation Status:** ⏳ **PARTIAL** (Phase 7B)
- Backend server running on localhost:8000 (local deployment)
- Production deployment to Railway/Vercel not yet completed
- Git repository initialized but not pushed to remote
- CI pipeline not set up

---

### DEC-028: Next.js Deployment (Vercel)

| | |
|---|---|
| **Status** | Accepted (Partial) |
| **Phase** | 7 |
| **Date** | 2026-06-02 |
| **Updated:** 2026-06-08 |

**Context:** Next.js frontend needs production hosting with CDN and preview branches.

**Options:**
1. Serve static export from FastAPI
2. **Vercel** (Next.js native)
3. Cloudflare Pages with Next adapter

**Decision:** **Vercel** connected to GitHub repo; production branch `main`.

**Rationale:** Zero-config Next.js deploy; automatic preview URLs for PRs after CI exists.

**Consequences:** Environment variables set in Vercel dashboard; no separate static CDN ADR needed.

**Implementation Status:** ⏳ **PARTIAL** (Phase 7B)
- Frontend file structure complete (38/38 checks passed)
- Next.js build not yet tested
- Vercel deployment not yet configured
- Git repository not pushed to remote

---

### DEC-029: Observability Stack

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 7 |
| **Date** | 2026-06-02 |
| **Updated:** 2026-06-08 |

**Context:** Architecture §11 defines metrics; v1 must trace requests without expensive APM.

**Options:**
1. Structured logs + PostgreSQL `audit_log` only
2. Above + **Grafana Cloud / Better Stack** log drain
3. Full OpenTelemetry + Datadog

**Decision:** v1 = **structured JSON logs** (trace_id) + **`audit_log` queries**; optional log drain if Phase 7 load test shows need.

**Rationale:** Meets monitoring strategy targets without vendor cost for MVP.

**Consequences:** Dashboard SQL/queries documented; alert rules manual until drain added.

**Implementation Status:** ✅ **COMPLETED** (Phase 7B)
- Structured logging implemented with trace IDs
- Audit log table exists and is being populated
- All E2E tests passed with proper logging
- Log drain deferred pending production traffic analysis

---

### DEC-030: Production Scaling Strategy

| | |
|---|---|
| **Status** | Accepted |
| **Phase** | 7 |
| **Date** | 2026-06-02 |
| **Updated:** 2026-06-08 |

**Context:** Target ≥10 concurrent trip plans without failure (eval 7.11).

**Options:**
1. Single instance until failure
2. **Horizontal FastAPI replicas** + shared Upstash + Supabase pooler
3. Kubernetes from day one

**Decision:** **2–4 stateless FastAPI instances** behind Railway/reverse proxy; state in Redis; **no K8s** for v1.

**Rationale:** Matches architecture §12; LangGraph stateless workers; cheapest scale step.

**Consequences:** Load test validates 10 concurrent; increase replicas if cache hit ≥40% and DB pool sufficient.

**Implementation Status:** ✅ **COMPLETED** (Phase 7B)
- Load testing completed with 10 concurrent users
- Pipeline success rate: 100% (50/50 requests passed)
- Concurrent user handling verified
- Horizontal scaling strategy validated
- No Kubernetes needed for v1

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| v1.4 | 2026-06-12 | Added DEC-033 (Google Translate TTS fallback) and DEC-034 (WAV container wrapping for Gemini PCM audio) to fix audio playback issues. |
| v1.3 | 2026-06-08 | Updated Phase 7 decision statuses based on implementation: DEC-004/005 Accepted (completed Phase 7A), DEC-027/028 Accepted (partial), DEC-029/030 Accepted (completed Phase 7B) |
| v1.2 | 2026-06-02 | DEC-032 local-first dev + Phase 7 managed migration; DEC-004/005 updated for dual environments |

---

> **Related Documents:**  
> - [phase-wise-implementationPlan.md](phase-wise-implementationPlan.md) — Tasks, Files Created, exit criteria per phase  
> - [eval.md](eval.md) — Phase sign-off checklists  
> - [architecture.md](architecture.md) — System design source of truth
