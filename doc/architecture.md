# Real-Time Voice AI Travel Planning Multi-Agent System — Architecture Document

> **Author:** Shiv
> **Date:** 2026-06-02
> **Status:** Architecture Blueprint
> **Source Docs:** [AIProductStrategy.md](AIProductStrategy.md) · [enhancedProblemStatement.md](enhancedProblemStatement.md)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Design Principles](#2-design-principles)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Layer-by-Layer Architecture](#4-layer-by-layer-architecture)
5. [Detailed Component Architecture](#5-detailed-component-architecture)
6. [Component Responsibilities & Key Interfaces](#6-component-responsibilities--key-interfaces)
7. [Data Flow & Sequence Diagrams](#7-data-flow--sequence-diagrams)
8. [Technology Stack](#8-technology-stack)
9. [Security Architecture & Principles](#9-security-architecture--principles)
10. [Error Handling Strategy](#10-error-handling-strategy)
11. [Monitoring & Logging Strategy](#11-monitoring--logging-strategy)
12. [Scalability Strategy](#12-scalability-strategy)
13. [Testing & Evaluation Strategy](#13-testing--evaluation-strategy)
14. [Ethical & Responsible AI Strategy](#14-ethical--responsible-ai-strategy)
15. [Risk Register](#15-risk-register)
16. [Deployment & Execution Strategy](#16-deployment--execution-strategy)
17. [Directory Structure (Final State)](#17-directory-structure-final-state)

---

## 1. System Overview

The **Real-Time Voice AI Travel Planning Multi-Agent System** is a production-grade platform that converts natural-language travel requests (voice or text) into personalized, validated, and budget-compliant itineraries. It employs a **Manager–Worker orchestration pattern with Sequential Synthesis**, powered by LangGraph, where specialized AI agents collaborate in parallel and sequential phases to deliver a complete travel plan in under 10 seconds.

```mermaid
flowchart LR
    subgraph User
        U["👤 Traveler"]
    end

    subgraph System["AI Travel Planning Platform"]
        direction TB
        IO["Input / Output Layer\n(Voice + Text + PDF + Email)"]
        ORCH["Orchestration Layer\n(LangGraph Multi-Agent Pipeline)"]
        TOOL["Tool Integration Layer\n(MCP Clients → External MCP Servers)"]
        DATA["Data & Memory Layer\n(PostgreSQL · Redis · Mem0)"]
    end

    subgraph External["External Services"]
        API["Flight · Hotel · Routing · Geocoding APIs"]
        LLM["LLM Providers\n(Groq · Gemini)"]
    end

    U <-->|Voice / Text| IO
    IO <--> ORCH
    ORCH <--> TOOL
    ORCH <--> DATA
    ORCH <--> LLM
    TOOL <--> API
```

**Core Capabilities:**
- **Voice-first interaction** — Plan trips hands-free via speech with editable transcript fallback
- **Multi-agent orchestration** — 8 specialized agents collaborate (4 parallel + 3 sequential + 1 manager)
- **Real-time data grounding** — All recommendations backed by live API data via MCP
- **Personalization** — Three-tier memory (short-term, long-term, episodic) for preference-aware planning
- **Self-correcting pipeline** — Validator-driven regeneration loop (max 3 iterations) ensures quality
- **Dual-brain model design** — Groq for speed-critical agents, Gemini for reasoning-critical agents

---

## 2. Design Principles

Six governing principles drive every architectural decision in this system. They are derived directly from the product strategy and are non-negotiable across all components.

| # | Principle | Description | Architectural Implication |
|---|-----------|-------------|--------------------------|
| 1 | **User Trust** | Users must trust the plan is accurate, bookable, and safe | Validator Agent + factual grounding (Nominatim/Maps verification) before any user-facing output; no hallucinated recommendations |
| 2 | **Cost Efficiency** | Minimize operational cost per trip plan without sacrificing quality | Dual-brain model split (Groq for speed, Gemini only for rigor); aggressive Redis caching; per-agent step limits |
| 3 | **Low Latency** | First useful output in <5 sec; full plan in <10 sec | Parallel worker execution; SSE streaming; tiered latency targets (1s → 5s → 10s) |
| 4 | **Reliability** | ≥99% pipeline success rate; graceful degradation on partial failures | Retry + fallback chains; circuit breakers; partial result preservation; worker independence |
| 5 | **Personalization** | Every plan reflects the user's unique preferences and history | Mem0 (long-term prefs) + PostgreSQL episodic memory (past trips) + LangGraph state (session context) |
| 6 | **Grounding** | Every claim must be backed by verifiable tool output | MCP tool-first reasoning; Nominatim location verification; no speculative recommendations |

**Additional Design Tenets:**

- **Separation of Concerns** — Each agent has a single well-defined responsibility; no agent does two jobs
- **Tool-Assisted Reasoning** — Agents prefer MCP tool calls over internal knowledge or speculation
- **Constraint-First Planning** — Budget, dates, and hard limits are resolved before preferences and nice-to-haves
- **Graph of Thought (GoT) Reasoning** — Agents reason via branching, backtracking, and merging — not linear chain-of-thought alone

---

## 3. High-Level Architecture

The system is structured as a **four-layer stack** with external service integrations:

```mermaid
flowchart TD
    subgraph IL["🎤 Input / Output Layer"]
        direction LR
        VI["Voice Input\n(Groq Whisper API + WebRTC VAD)"]
        TI["Text Input"]
        WEB["Web UI\n(Desktop-First Responsive)"]
        PDF["PDF Report\nGenerator"]
        EMAIL["Email Delivery\n(Gmail MCP)"]
        TTS["Voice Summary\n(ElevenLabs TTS)"]
    end

    subgraph AL["🔐 Auth Layer"]
        direction LR
        AUTH["Supabase Auth\n(Email/Password + Google OAuth)"]
    end

    subgraph OL["🧠 Orchestration Layer"]
        direction TB
        subgraph Manager
            PA["Planner Agent\n(Groq)"]
        end
        subgraph PW["Parallel Workers"]
            direction LR
            FA["Flight Agent\n(Groq)"]
            HA["Hotel Agent\n(Groq)"]
            AA["Attraction Agent\n(Groq)"]
            TA["Transport Agent\n(Groq)"]
        end
        subgraph SS["Sequential Synthesis"]
            direction LR
            BA["Budget Agent\n(Gemini)"]
            IC["Itinerary Composer\n(Groq)"]
            VA["Validator / Critic\n(Gemini)"]
        end

        PA --> PW
        PW --> BA
        BA --> IC
        IC --> VA
        VA -->|"Issues (≤3 loops)"| PA
    end

    subgraph TL["🔧 Tool Integration Layer (MCP Clients)"]
        direction LR
        MCP1["AviationStack\nMCP Client"]
        MCP2["Tavily Search\nMCP Client"]
        MCP3["GraphHopper/OSRM\nMCP Client"]
        MCP4["Nominatim\nMCP Client"]
        MCP5["Gmail\nMCP Client"]
    end

    subgraph DL["💾 Data & Memory Layer"]
        direction LR
        PG["Supabase PostgreSQL\n(Users · Trips · Episodic Memory · Audit)"]
        RD["Upstash Redis\n(Session Cache · API Cache · Agent State)"]
        M0["Mem0\n(Long-Term Preferences)"]
    end

    IL <--> AL
    AL <--> OL
    OL <--> TL
    OL <--> DL
    FA <--> MCP1
    HA <--> MCP2
    AA <--> MCP2
    AA <--> MCP4
    TA <--> MCP3
    TA <--> MCP4
    VA <--> MCP4
    EMAIL <--> MCP5
    PA <--> M0
    PA <--> PG
```

---

## 4. Layer-by-Layer Architecture

### 4.1 Input / Output Layer

Handles all user-facing interactions — voice capture, text input, plan rendering, and deliverable generation.

```mermaid
flowchart LR
    subgraph Input
        MIC["🎙️ Microphone"] --> VAD["WebRTC VAD\n(Speech Detection)"]
        VAD --> STT["Groq Whisper API\n(Speech-to-Text)"]
        STT --> TRANS["Editable\nTranscript"]
        KB["⌨️ Text Input"] --> TRANS
    end

    subgraph Processing
        TRANS --> API["FastAPI\nBackend"]
        API --> SSE["SSE Stream\n(Real-Time Updates)"]
    end

    subgraph Output
        SSE --> UI["Web UI\n(Itinerary View)"]
        API --> PDFG["PDF Generator"]
        API --> EMLS["Gmail MCP\n(Email Sender)"]
        API --> TTSE["ElevenLabs TTS\n(Voice Summary)"]
    end
```

| Sub-Component | Role | Technology |
|---------------|------|------------|
| **WebRTC VAD** | Detect speech start/end for cost control; only process active speech | WebRTC Voice Activity Detection |
| **Groq Whisper API** | Convert speech audio to text transcript | Groq cloud API (`whisper-large-v3-turbo`) — no local model |
| **Editable Transcript** | Allow user to review and correct STT output before submission | Frontend UI component |
| **SSE Stream** | Push real-time pipeline status to frontend ("Searching flights…", "Composing itinerary…") | Server-Sent Events via FastAPI |
| **PDF Generator** | Produce branded, downloadable trip report | Python PDF library (e.g., ReportLab / WeasyPrint) |
| **ElevenLabs TTS** | Generate 30–45 sec audio summary (opt-in only, voice mode) | ElevenLabs API |
| **Gmail MCP** | Send itinerary + PDF + voice summary link to user's email | Gmail API via MCP server |

---

### 4.2 Auth Layer

```mermaid
flowchart LR
    U["User"] --> LP["Login / Register Page"]
    LP --> EP["Email + Password"]
    LP --> GO["Google OAuth"]
    EP --> SA["Supabase Auth"]
    GO --> SA
    SA --> JWT["JWT Token"]
    JWT --> API["FastAPI Backend\n(Protected Routes)"]
    SA --> RLS["Row Level Security\n(PostgreSQL)"]
```

| Concern | Detail |
|---------|--------|
| **Providers** | Email/password + Google OAuth |
| **Token Management** | JWT issued by Supabase; verified on every API call |
| **Data Isolation** | Supabase Row Level Security (RLS) ensures users only access their own data |
| **Session Persistence** | Redis stores active session metadata for fast lookup |

---

### 4.3 Orchestration Layer (LangGraph)

The core agent pipeline — the "brain" of the system. Uses LangGraph `StateGraph` for workflow management.

```mermaid
flowchart TD
    INPUT["User Request\n(Structured Constraints)"]
    PA["Planner Agent\n(Manager)"]
    DL{"Discovery\nComplete?"}
    FUQ["Follow-Up\nQuestion"]
    URA["User\nAnswer"]

    subgraph PARALLEL["⚡ Parallel Phase (2–4 sec)"]
        direction LR
        FA["Flight\nAgent"]
        HA["Hotel\nAgent"]
        AA["Attraction\nAgent"]
        TA["Transport\nAgent"]
    end

    subgraph SEQUENTIAL["🔗 Sequential Phase"]
        direction TB
        BA["Budget\nAgent"]
        IC["Itinerary\nComposer"]
        VA["Validator\n/ Critic"]
    end

    DELIVER["✅ Delivery"]
    WARN["⚠️ Deliver with Warnings"]

    INPUT --> PA
    PA --> DL
    DL -->|No| FUQ
    FUQ --> URA
    URA --> PA
    DL -->|Yes| PARALLEL
    PARALLEL --> BA
    BA --> IC
    IC --> VA
    VA -->|Approved| DELIVER
    VA -->|"Issues (regen < 3)"| PA
    VA -->|"Max regen reached"| WARN
```

**LangGraph State** — the single source of truth shared across all agents:

| State Key | Type | Written By | Read By |
|-----------|------|------------|---------|
| `raw_input` | string | Input Layer | Planner |
| `input_mode` | "voice" \| "text" | Input Layer | Planner, Output Layer |
| `destinations` | string[] | Planner | All Workers |
| `dates` | object | Planner | Flight, Hotel, Transport |
| `budget` | object | Planner | Budget Agent |
| `travelers` | object | Planner | Flight, Hotel |
| `preferences` | object | Planner (via Mem0) | All Agents |
| `flight_results` | object | Flight Agent | Budget, Composer |
| `hotel_results` | object | Hotel Agent | Budget, Composer |
| `attraction_results` | object | Attraction Agent | Budget, Composer |
| `transport_results` | object | Transport Agent | Budget, Composer |
| `budget_report` | object | Budget Agent | Composer, Validator |
| `composed_itinerary` | object | Composer | Validator |
| `validation_result` | object | Validator | Delivery / Planner (regen) |
| `regeneration_count` | int | Validator | Validator, Planner |
| `current_phase` | string | Orchestrator | All (control flow) |
| `errors` | object[] | Any Agent | Error Handler |
| `trace_id` | string | System | All (observability) |

---

### 4.4 Tool Integration Layer (MCP Clients)

This project implements **MCP Clients** that connect to **External MCP Servers** (hosted and managed in a separate project). All external API access is routed through these MCP Clients — not ad hoc HTTP wrappers. The MCP Client layer enforces **schema validation, error handling & retry, rate limiting, response caching, and audit logging** before every outbound call to an external MCP server.

> [!IMPORTANT]
> **MCP Servers are NOT part of this project.** They are hosted externally in a separate project. This project only implements the **MCP Client** with a middleware layer that wraps every outbound tool call with the five safeguards listed above.

```mermaid
flowchart TD
    subgraph Agents
        FA["Flight Agent"]
        HA["Hotel Agent"]
        AA["Attraction Agent"]
        TA["Transport Agent"]
        VA["Validator Agent"]
        DL["Delivery System"]
    end

    subgraph MCP["MCP Client Middleware (This Project)"]
        direction TB
        SV["Schema Validation"]
        EH["Error Handling\n& Retry (Exp. Backoff)"]
        RL["Rate Limiting"]
        CA["Response Caching\n(Redis)"]
        AL["Audit Logging"]
    end

    subgraph APIs["External MCP Servers (Hosted Separately)"]
        AS["AviationStack\n(Flights)"]
        TV["Tavily Search\n(Hotels · Attractions)"]
        GH["GraphHopper / OSRM\n(Routing)"]
        NM["Nominatim\n(Geocoding)"]
        GM["Gmail\n(Email)"]
    end

    FA --> MCP --> AS
    HA --> MCP --> TV
    AA --> MCP --> TV
    AA --> MCP --> NM
    TA --> MCP --> GH
    TA --> MCP --> NM
    VA --> MCP --> NM
    DL --> MCP --> GM
```

**MCP Client Middleware Responsibilities (Applied Before Every External MCP Call):**

| # | Middleware Layer | Responsibility | Execution Order |
|---|-----------------|----------------|------------------|
| 1 | **Schema Validation** | Validate tool arguments against defined schemas before sending to external MCP server; validate response schemas on return | Pre-call + Post-call |
| 2 | **Error Handling & Retry** | Catch transient failures (network timeout, rate limit, 5xx); retry with exponential backoff (max 3 attempts) | On failure |
| 3 | **Rate Limiting** | Enforce per-API rate limits to prevent quota exhaustion on external MCP servers | Pre-call gate |
| 4 | **Response Caching** | Cache API responses in Redis with configurable TTL per API; check cache before making external call | Pre-call (read) + Post-call (write) |
| 5 | **Audit Logging** | Log every tool call with trace ID, agent, tool, arguments, result, latency, cost, cache hit | Post-call (always) |

**MCP Client → External MCP Server Assignment Matrix:**

| External MCP Server | MCP Client Used By | Access Pattern |
|---------------------|--------------------|-----------------|
| **AviationStack** | Flight Agent (exclusive) | Flight search, pricing, availability |
| **Tavily Search** | Planner, Hotel Agent, Attraction Agent | Destination research, hotel/attraction discovery |
| **GraphHopper / OSRM** | Transport Agent (exclusive) | Route calculation, travel-time estimation |
| **Nominatim** | Attraction Agent, Transport Agent, Validator | Geocoding, location existence validation |
| **Gmail** | Delivery System (not an agent) | Itinerary email delivery |

---

### 4.5 Data & Memory Layer

```mermaid
flowchart TD
    subgraph Memory["Three-Tier Memory Architecture"]
        direction TB
        subgraph ST["Short-Term Memory"]
            LGS["LangGraph State\n(Active session context)"]
            RDS["Upstash Redis\n(Session cache · API cache · agent state)"]
        end
        subgraph LT["Long-Term Memory"]
            MEM["Mem0\n(Food prefs · travel style · accommodation ·\ntransport · activity preferences)"]
        end
        subgraph EP["Episodic Memory"]
            PGE["Supabase PostgreSQL\n(Past trips · lessons learned ·\nwhat worked / didn't)"]
        end
    end

    PA["Planner Agent"] <-->|Full access| MEM
    PA <-->|Full access| PGE
    PA <-->|Session read/write| LGS & RDS
    WA["Worker Agents"] <-->|Curated context\nfrom Planner| LGS & RDS
    BA["Budget Agent"] <-->|Budget prefs only| LGS
    CO["Composer"] <-->|Full prefs for\npersonalization| LGS
    VA["Validator"] <-->|Prefs for\nalignment check| LGS
```

| Memory Tier | Scope | Storage | Freshness | Access Pattern |
|-------------|-------|---------|-----------|----------------|
| **Short-Term** | Current conversation and planning session | LangGraph State + Redis | Current session only | All agents (via state) |
| **Long-Term** | Cross-trip user preferences and habits | Mem0 | Persistent; user-editable | Planner retrieves → curates → passes to workers |
| **Episodic** | Past travel experiences and lessons | PostgreSQL (Supabase) | 1-year retention window | Planner reads for repeat destinations and learned patterns |

**Data stored in PostgreSQL (Supabase):**

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `profiles` | User identity and settings | id, display_name, email, avatar_url |
| `trips` | Trip metadata and constraints | user_id, title, raw_request, constraints (JSONB), status |
| `itineraries` | Final validated plan output | trip_id, content (JSONB), budget_breakdown, validation_status, version |
| `episodic_memory` | Past trip learnings | user_id, destination, summary, lessons_learned (JSONB), expires_at |
| `chat_messages` | Conversation history | trip_id, role, content, metadata (trace_id, agent) |
| `audit_log` | Agent action trace records | trace_id, agent, tool, arguments, result, latency_ms, cost_usd, cache_hit |

#### Database Schema DDL

```sql
-- =============================================
-- Users & Auth (managed by Supabase Auth)
-- =============================================

-- User Profiles
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id),
    display_name TEXT,
    email TEXT UNIQUE NOT NULL,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trip Plans
CREATE TABLE trips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    raw_request TEXT,
    constraints JSONB,         -- {budget, dates, travelers, preferences}
    status TEXT DEFAULT 'planning',  -- planning | completed | failed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Itineraries (final validated output)
CREATE TABLE itineraries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID REFERENCES trips(id) ON DELETE CASCADE,
    content JSONB NOT NULL,     -- Day-by-day structured itinerary
    budget_breakdown JSONB,
    validation_status TEXT,     -- approved | warnings | rejected
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Episodic Memory (past trip learnings)
CREATE TABLE episodic_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    trip_id UUID REFERENCES trips(id),
    destination TEXT,
    summary TEXT,
    lessons_learned JSONB,     -- What worked, what didn't
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ       -- 1-year freshness window
);

-- Chat History
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID REFERENCES trips(id) ON DELETE CASCADE,
    role TEXT NOT NULL,          -- user | assistant | system
    content TEXT NOT NULL,
    metadata JSONB,             -- {agent, tool, trace_id}
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Log (agent observability)
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id TEXT NOT NULL,
    trip_id UUID REFERENCES trips(id),
    agent TEXT NOT NULL,
    model TEXT,
    tool TEXT,
    arguments JSONB,
    result JSONB,
    latency_ms INTEGER,
    cost_usd NUMERIC(10, 6),
    cache_hit BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. Detailed Component Architecture

### 5.1 Agent Component Diagram

```mermaid
flowchart TD
    subgraph MANAGER["Manager"]
        PA["Planner Agent\n─────────────\nModel: Groq\nMax Steps: 5\n─────────────\nIntent Parsing\nConstraint Extraction\nMemory Retrieval\nTask Delegation\nFollow-Up Q&A\nIteration Handling"]
    end

    subgraph WORKERS["Parallel Workers"]
        direction LR
        FA["Flight Agent\n─────────────\nModel: Groq\nMax Steps: 3\n─────────────\nFlight Search\nPrice Filtering\nAvailability Check\nAlternative Suggestions"]
        HA["Hotel Agent\n─────────────\nModel: Groq\nMax Steps: 3\n─────────────\nHotel Discovery\nLocation Filtering\nAmenity Matching\nPrice Comparison"]
        AA["Attraction Agent\n─────────────\nModel: Groq\nMax Steps: 3\n─────────────\nPOI Discovery\nRestaurant Recs\nExistence Validation\nCrowd-Timing Logic"]
        TA["Transport Agent\n─────────────\nModel: Groq\nMax Steps: 3\n─────────────\nInter-City Routes\nLocal Transit\nTravel-Time Calc\nMulti-Modal Options"]
    end

    subgraph SYNTH["Sequential Synthesis"]
        BA["Budget Agent\n─────────────\nModel: Gemini\nMax Steps: 2\n─────────────\nCost Aggregation\nBudget Compliance\nOptimization\nBreakdown Report"]
        IC["Itinerary Composer\n─────────────\nModel: Groq\nMax Steps: 3\n─────────────\nSchedule Assembly\nGeo-Clustering\nPersonalization\nMeal Scheduling"]
        VA["Validator / Critic\n─────────────\nModel: Gemini\nMax Steps: 2\n─────────────\nQuality Checks\nConflict Detection\nFactual Grounding\nBudget Re-Check"]
    end

    PA -->|"Delegate"| FA & HA & AA & TA
    FA & HA & AA & TA -->|"Results"| BA
    BA -->|"Budget Report"| IC
    IC -->|"Draft Itinerary"| VA
    VA -->|"Approved"| OUT["Delivery"]
    VA -->|"Issues"| PA
```

### 5.2 Dual-Brain Model Architecture

The system deliberately splits **research/synthesis** from **budget/validation** across two LLM families:

```mermaid
flowchart LR
    subgraph GROQ["⚡ Groq Brain — Speed"]
        direction TB
        G1["Planner Agent"]
        G2["Flight Agent"]
        G3["Hotel Agent"]
        G4["Attraction Agent"]
        G5["Transport Agent"]
        G6["Itinerary Composer"]
    end

    subgraph GEMINI["🧠 Gemini Brain — Rigor"]
        direction TB
        GE1["Budget Agent"]
        GE2["Validator / Critic Agent"]
    end

    GROQ ---|"Fast research,\noption generation,\ncreative synthesis"| LLM1["Groq Cloud API"]
    GEMINI ---|"Structured reasoning,\narithmetic,\ncompliance checks"| LLM2["Google Gemini API"]
```

| Brain | Agents | Strengths Used | Latency Profile |
|-------|--------|----------------|-----------------|
| **Groq** | Planner, Flight, Hotel, Attraction, Transport, Composer | Fast inference, creative synthesis, option generation | < 1 sec per agent call |
| **Gemini** | Budget Agent, Validator/Critic | Structured reasoning, arithmetic accuracy, compliance critique | 1–2 sec per agent call |

### 5.3 Self-Correcting Loop Architecture

```mermaid
flowchart TD
    IC["Itinerary Composer"] --> VA["Validator / Critic"]
    VA --> CHK{"Issues\nFound?"}
    CHK -->|"No"| APPROVE["✅ Approved\n→ Delivery"]
    CHK -->|"Yes"| REGEN{"regen_count\n< 3?"}
    REGEN -->|"Yes"| FB["Validator sends\nspecific feedback"]
    FB --> PA["Planner re-plans\naffected segments"]
    PA --> RW["Re-run only\naffected workers"]
    RW --> BA["Budget Agent\n(re-aggregate)"]
    BA --> IC
    REGEN -->|"No"| WARN["⚠️ Deliver with\nwarnings + human override"]

    style APPROVE fill:#4caf50,color:#fff
    style WARN fill:#ff9800,color:#000
```

**Issue categories and actions:**

| Category | Examples | Action |
|----------|----------|--------|
| **Critical** | Non-existent attractions, impossible routing, severe budget violation | Auto-reject → trigger regeneration |
| **Major** | <30 min buffer between activities, overlapping activities, closed attractions | Auto-reject → trigger regeneration |
| **Minor** | Suboptimal scheduling, food preference soft mismatch | Warn → allow human override |

### 5.4 Latency Budget

The end-to-end latency budget allocates time across pipeline components to meet the <10 sec target:

| Component | Allocation | Running Total |
|-----------|-----------|---------------|
| STT (voice input) | < 1 sec | 1 sec |
| Planner Agent (intent parsing + memory lookup) | < 1 sec | 2 sec |
| Parallel Workers (Flight, Hotel, Attraction, Transport — concurrent) | 2–4 sec | 6 sec |
| Budget Agent (deterministic arithmetic) | < 1 sec | 7 sec |
| Itinerary Composer (scheduling logic) | 1–2 sec | 9 sec |
| Validator Agent (validation checks) | 1–2 sec | 10 sec |
| **Total (worst case)** | **< 10 sec** | — |
| **Total (streaming first useful output)** | **< 5 sec** | — |

> [!NOTE]
> Streaming begins at **1–2 seconds** with a plan skeleton. The user sees "Searching flights…", "Finding hotels…" status updates via SSE while parallel workers execute. Full enriched itinerary appears at **< 10 seconds**.

---

## 6. Component Responsibilities & Key Interfaces

### 6.1 Planner Agent (Manager)

| Aspect | Detail |
|--------|--------|
| **Role** | Central coordinator — understands intent, extracts constraints, delegates, orchestrates |
| **Model** | Groq |
| **Max Steps** | 5 |

**Responsibilities:**
- Parse voice transcripts and text into structured constraints
- Retrieve user preferences from Mem0 and episodic memory from PostgreSQL
- Identify missing critical info → ask follow-up questions (1 at a time, max 2–3 total: dates → budget → travelers)
- Reuse stored preferences — never re-ask known information
- Create delegation plan and dispatch to parallel worker agents
- Handle user follow-up questions and plan iteration requests
- Receive Validator feedback and coordinate selective re-planning

**Key Interfaces:**

| Interface | Direction | Data |
|-----------|-----------|------|
| `User → Planner` | Input | Raw request (text/voice transcript) |
| `Mem0 → Planner` | Input | User preference profile |
| `PostgreSQL → Planner` | Input | Episodic memory (past trips) |
| `Planner → User` | Output | Follow-up questions |
| `Planner → Workers` | Output | Structured constraints + curated preference context |
| `Validator → Planner` | Input | Specific regeneration feedback |

---

### 6.2 Flight Agent (Parallel Worker)

| Aspect | Detail |
|--------|--------|
| **Role** | Research and validate flight options matching user constraints |
| **Model** | Groq |
| **Max Steps** | 3 |
| **MCP Tools** | AviationStack API |

**Responsibilities:**
- Search flights by origin, destination, dates, traveler count
- Filter by price, duration, airline preferences (from Mem0 context)
- Return top 3–5 options with pricing, timing, booking URLs
- Handle no-results with alternative date/route suggestions

**Key Interfaces:**

| Interface | Direction | Data |
|-----------|-----------|------|
| `Planner → Flight` | Input | Origin, destination, dates, travelers, budget, airline prefs |
| `Flight → Budget` | Output | Flight options list + total estimated flight cost |
| `Flight → AviationStack MCP` | Tool Call | Search queries |

---

### 6.3 Hotel Agent (Parallel Worker)

| Aspect | Detail |
|--------|--------|
| **Role** | Research and recommend hotels based on location, budget, and preferences |
| **Model** | Groq |
| **Max Steps** | 3 |
| **MCP Tools** | Tavily Search |

**Responsibilities:**
- Search hotels in target destinations
- Filter by proximity to attractions/transit, price, amenities
- Apply accommodation preferences (budget vs. luxury, specific amenities)
- Return top 3–5 options with pricing, location, booking URLs

**Key Interfaces:**

| Interface | Direction | Data |
|-----------|-----------|------|
| `Planner → Hotel` | Input | Destinations, dates, budget allocation, accommodation prefs |
| `Hotel → Budget` | Output | Hotel options list + total estimated accommodation cost |
| `Hotel → Tavily MCP` | Tool Call | Search queries |

---

### 6.4 Attraction Agent (Parallel Worker)

| Aspect | Detail |
|--------|--------|
| **Role** | Discover and validate attractions, restaurants, and points of interest |
| **Model** | Groq |
| **Max Steps** | 3 |
| **MCP Tools** | Tavily Search, Nominatim |

**Responsibilities:**
- Search attractions matching user interests (food, temples, museums, etc.)
- Validate attraction existence via Nominatim geocoding
- Apply crowd-timing logic (popular sites → early morning)
- Include restaurant recommendations based on food preferences
- Return top 5–10 attractions with descriptions, hours, fees

**Key Interfaces:**

| Interface | Direction | Data |
|-----------|-----------|------|
| `Planner → Attraction` | Input | Destinations, interests, crowd tolerance, food prefs |
| `Attraction → Budget` | Output | Attraction/restaurant list + estimated activity costs |
| `Attraction → Tavily MCP` | Tool Call | Discovery queries |
| `Attraction → Nominatim MCP` | Tool Call | Location validation |

---

### 6.5 Transport Agent (Parallel Worker)

| Aspect | Detail |
|--------|--------|
| **Role** | Plan inter-city and local transportation routes |
| **Model** | Groq |
| **Max Steps** | 3 |
| **MCP Tools** | GraphHopper / OSRM, Nominatim |

**Responsibilities:**
- Calculate inter-city transport options (flights, trains, buses)
- Plan local routes between attractions (transit, taxi, walking)
- Estimate travel times and costs for all segments
- Provide multiple options: fastest, cheapest, most convenient

**Key Interfaces:**

| Interface | Direction | Data |
|-----------|-----------|------|
| `Planner → Transport` | Input | Cities, attraction locations, dates, transport prefs |
| `Transport → Budget` | Output | Transport plan + total estimated transport cost |
| `Transport → GraphHopper MCP` | Tool Call | Routing queries |
| `Transport → Nominatim MCP` | Tool Call | Geocoding |

---

### 6.6 Budget Agent (Sequential)

| Aspect | Detail |
|--------|--------|
| **Role** | Aggregate costs, enforce budget compliance, optimize when over budget |
| **Model** | Gemini (structured arithmetic reasoning) |
| **Max Steps** | 2 |
| **MCP Tools** | None (deterministic logic) |

**Responsibilities:**
- Aggregate costs from all 4 worker agents
- Compare total against user budget constraint
- If within budget → proceed with breakdown
- If over budget → auto-optimize (adjust hotels → reduce attractions → change dates)
- Emit detailed budget compliance report for downstream agents

**Key Interfaces:**

| Interface | Direction | Data |
|-----------|-----------|------|
| `All Workers → Budget` | Input | Cost estimates per category |
| `Planner → Budget` | Input | User budget constraint + strict flag |
| `Budget → Composer` | Output | Budget compliance report + detailed breakdown |

**Budget compliance logic:**

| Condition | Status | Action |
|-----------|--------|--------|
| `total ≤ budget` | ✅ Within Budget | Proceed to Composer |
| `budget < total ≤ budget × 1.10` AND not strict | ⚠️ Warning | Proceed with optimization suggestions |
| `total > budget × 1.10` OR strict mode | 🚫 Over Budget | Auto-optimize → re-run affected workers if needed |

---

### 6.7 Itinerary Composer Agent (Sequential)

| Aspect | Detail |
|--------|--------|
| **Role** | Merge all worker outputs into a coherent, personalized day-by-day itinerary |
| **Model** | Groq (creative synthesis) |
| **Max Steps** | 3 |
| **MCP Tools** | None (synthesis and scheduling logic) |

**Responsibilities:**
- Merge flight, hotel, attraction, and transport outputs
- Create day-by-day schedule with realistic timing
- Apply personalization: crowd-avoidance timing, food preferences, travel style
- Group activities by geographic proximity
- Schedule meals with preference-aligned restaurants
- Add buffer time (≥30 min) between activities

**Key Interfaces:**

| Interface | Direction | Data |
|-----------|-----------|------|
| `Budget → Composer` | Input | Budget report + all worker outputs (via state) |
| `Mem0 (via state) → Composer` | Input | Full user preference context |
| `Composer → Validator` | Output | Structured day-by-day draft itinerary |

---

### 6.8 Validator / Critic Agent (Sequential)

| Aspect | Detail |
|--------|--------|
| **Role** | Validate composed itinerary for quality, completeness, and factual grounding |
| **Model** | Gemini (structured reasoning for critique) |
| **Max Steps** | 2 |
| **MCP Tools** | Nominatim (location validation) |

**Responsibilities:**
- Validate plan quality and completeness
- Re-check budget compliance
- Detect conflicts (overlapping cities same morning, impossible timing)
- Verify factual grounding (all places exist via Nominatim)
- Validate preference alignment (crowd-avoidance, food prefs)
- Approve, reject, or trigger self-correcting loop (max 3 iterations)

**Key Interfaces:**

| Interface | Direction | Data |
|-----------|-----------|------|
| `Composer → Validator` | Input | Draft itinerary |
| `Budget → Validator` | Input | Budget compliance report |
| `State → Validator` | Input | User constraints + preferences |
| `Validator → Delivery` | Output | Approved final plan |
| `Validator → Planner` | Output | Specific feedback for regeneration |
| `Validator → Nominatim MCP` | Tool Call | Location existence checks |

**Validation checklist:**

| Check | Category | Failure Action |
|-------|----------|----------------|
| All places exist on Maps/Nominatim | Critical | Reject → regen |
| No travel-time conflicts (same city twice in one morning) | Critical | Reject → regen |
| Budget compliance | Critical | Reject → regen |
| Attractions open on scheduled day | Major | Reject → regen |
| ≥30 min buffer between activities | Major | Reject → regen |
| Crowd-avoidance preferences respected | Minor | Warn → allow override |
| Food preference alignment | Minor | Warn → allow override |
| Scheduling could be more optimal | Minor | Warn → allow override |

---

## 7. Data Flow & Sequence Diagrams

### 7.1 End-to-End Trip Planning Sequence

```mermaid
sequenceDiagram
    actor User
    participant UI as Web UI
    participant API as FastAPI
    participant Auth as Supabase Auth
    participant PA as Planner Agent
    participant Mem0 as Mem0
    participant PG as PostgreSQL
    participant FA as Flight Agent
    participant HA as Hotel Agent
    participant AA as Attraction Agent
    participant TA as Transport Agent
    participant BA as Budget Agent
    participant IC as Itinerary Composer
    participant VA as Validator / Critic
    participant Redis as Redis Cache

    User->>UI: Voice/Text trip request
    UI->>API: POST /api/trips/plan
    API->>Auth: Verify JWT
    Auth-->>API: ✅ Authenticated

    API->>PA: Start planning pipeline
    PA->>Mem0: Retrieve user preferences
    Mem0-->>PA: {food: vegetarian, style: cultural, crowd: low}
    PA->>PG: Retrieve episodic memory
    PG-->>PA: Past trips & lessons

    alt Missing Information
        PA-->>UI: Follow-up question (SSE)
        User->>UI: Answer
        UI->>PA: User answer
    end

    Note over PA: All constraints extracted

    par Parallel Execution (2–4 sec)
        PA->>FA: Delegate flight search
        FA->>Redis: Check cache
        Redis-->>FA: Cache miss
        FA->>FA: AviationStack MCP call
        FA-->>BA: Flight results

        PA->>HA: Delegate hotel search
        HA->>Redis: Check cache
        HA->>HA: Tavily MCP call
        HA-->>BA: Hotel results

        PA->>AA: Delegate attraction search
        AA->>AA: Tavily + Nominatim MCP calls
        AA-->>BA: Attraction results

        PA->>TA: Delegate transport planning
        TA->>TA: GraphHopper + Nominatim MCP calls
        TA-->>BA: Transport results
    end

    Note over BA: All worker results received

    BA->>BA: Aggregate costs, check budget
    BA-->>IC: Budget compliance report

    IC->>IC: Compose day-by-day itinerary
    IC-->>VA: Draft itinerary

    VA->>VA: Validate quality, grounding, conflicts
    
    alt Validation Passed
        VA-->>API: ✅ Approved final plan
        API-->>UI: Full itinerary (SSE)
        API->>API: Generate PDF
        API->>API: Send email (Gmail MCP)
        API->>API: Generate voice summary (ElevenLabs)
    else Validation Failed (regen < 3)
        VA-->>PA: Specific feedback
        Note over PA: Re-plan affected segments only
    else Max Regen Reached
        VA-->>API: ⚠️ Plan with warnings
    end
```

### 7.2 Voice Input Processing Flow

```mermaid
sequenceDiagram
    actor User
    participant MIC as Microphone
    participant VAD as WebRTC VAD
    participant STT as Groq Whisper API
    participant UI as Web UI
    participant API as FastAPI

    User->>MIC: Starts speaking
    MIC->>VAD: Audio stream
    VAD->>VAD: Detect speech start
    VAD->>STT: Buffer audio (speech only)
    User->>MIC: Stops speaking
    VAD->>VAD: Detect speech end
    STT->>STT: Transcribe audio
    STT-->>UI: Text transcript
    UI-->>User: Show editable transcript
    User->>UI: Confirm / Edit transcript
    UI->>API: Submit final text
```

### 7.3 Follow-Up Discovery Flow

```mermaid
sequenceDiagram
    actor User
    participant PA as Planner Agent
    participant Mem0 as Mem0

    User->>PA: "I want to visit Japan"
    PA->>Mem0: Check stored preferences
    Mem0-->>PA: {budget_pref: budget, food: vegetarian}
    
    Note over PA: Missing: dates, travelers

    PA-->>User: "What dates are you considering?"
    User->>PA: "March 15 to 20"
    
    PA-->>User: "How many travelers?"
    User->>PA: "Just me, solo trip"
    
    Note over PA: Sufficient info + Mem0 prefs → delegate to workers
    PA->>PA: Create execution plan
```

### 7.4 Budget Violation & Optimization Flow

```mermaid
sequenceDiagram
    participant Workers as All Workers
    participant BA as Budget Agent
    participant IC as Itinerary Composer
    participant PA as Planner Agent

    Workers-->>BA: Total costs: $3,800
    Note over BA: Budget: $3,000 → Over by $800

    alt Not Strict Mode
        BA->>BA: Auto-optimize
        Note over BA: Downgrade hotel ($400 → $250/night)
        Note over BA: Remove 1 paid attraction ($50)
        BA-->>IC: Adjusted budget report ($2,950)
    else Strict Mode
        BA-->>PA: Over-budget → request re-planning
        PA->>PA: Adjust constraints
        PA->>Workers: Re-run with tighter budget
    end
```

---

## 8. Technology Stack

### 8.1 Complete Technology Map

```mermaid
flowchart TD
    subgraph Frontend["Frontend"]
        direction LR
        NEXT["Next.js 14+\n(App Router)"]
        TS["TypeScript"]
        TW["Tailwind CSS"]
        RESP["Responsive Design\n(Desktop-First)"]
    end

    subgraph Backend["Backend"]
        direction LR
        FAPI["FastAPI"]
        ASYNC["AsyncIO"]
        PY["Python 3.11+"]
    end

    subgraph Orchestration["Agent Orchestration"]
        direction LR
        LG["LangGraph"]
        LC["LangChain"]
    end

    subgraph LLMs["LLM Providers"]
        direction LR
        GROQ["Groq\n(Research/Synthesis)"]
        GEM["Gemini\n(Budget/Validation)"]
    end

    subgraph ToolLayer["Tool Integration"]
        direction LR
        MCP["Model Context\nProtocol (MCP)"]
    end

    subgraph DataStores["Data Stores"]
        direction LR
        SUPA["Supabase\n(PostgreSQL + Auth)"]
        UPST["Upstash Redis\n(Cache)"]
        MEM0["Mem0\n(Long-Term Memory)"]
    end

    subgraph Voice["Voice Pipeline"]
        direction LR
        GW["Groq Whisper API\n(STT)"]
        WVAD["WebRTC VAD"]
        EL["ElevenLabs\n(TTS)"]
    end

    subgraph ExternalAPIs["External APIs (via MCP)"]
        direction LR
        AVIS["AviationStack"]
        TAVI["Tavily Search"]
        GHOP["GraphHopper / OSRM"]
        NOMI["Nominatim"]
        GMAI["Gmail API"]
    end

    Frontend <--> Backend
    Backend <--> Orchestration
    Orchestration <--> LLMs
    Orchestration <--> ToolLayer
    ToolLayer <--> ExternalAPIs
    Backend <--> DataStores
    Backend <--> Voice
```

### 8.2 Stack Breakdown by Layer

| Layer | Technology | Role |
|-------|-----------|------|
| **Frontend** | Next.js 14+ (App Router, TypeScript, Tailwind CSS) | Desktop-first responsive web UI; deploy to Vercel |
| **Backend** | FastAPI + AsyncIO (Python 3.11+) | REST API, SSE streaming, business logic |
| **Orchestration** | LangGraph + LangChain | Multi-agent workflow management, state graph |
| **LLMs** | Groq (research/synthesis agents), Gemini (budget/validation agents) | Dual-brain AI inference |
| **Tool Integration** | Model Context Protocol (MCP) | Standardized agent ↔ tool interface |
| **Auth** | Supabase Auth | Email/password + Google OAuth, JWT tokens |
| **Database** | Supabase PostgreSQL | Users, trips, itineraries, episodic memory, audit log |
| **Cache** | Upstash Redis | Session cache, API response cache, agent state |
| **Long-Term Memory** | Mem0 | User preference storage and retrieval |
| **STT** | Groq Whisper API + WebRTC VAD | Voice-to-text with speech activity detection |
| **TTS** | ElevenLabs | Voice summary generation (opt-in) |
| **Flight API** | AviationStack (via MCP) | Flight discovery and pricing |
| **Search API** | Tavily Search (via MCP) | Hotel, attraction, destination research |
| **Routing API** | GraphHopper / OSRM (via MCP) | Route calculation, travel-time estimation |
| **Geocoding API** | Nominatim (via MCP) | Location validation, coordinate lookup |
| **Email API** | Gmail (via MCP) | Itinerary and summary delivery |
| **PDF Generation** | ReportLab / WeasyPrint | Downloadable trip report |

---

## 9. Security Architecture & Principles

### 9.1 Security Architecture Diagram

```mermaid
flowchart TD
    subgraph Perimeter["Perimeter Security"]
        RL["Rate Limiting\n(Per-user: 10 req/hr)"]
        IL["Input Length Limits\n(Text: 500 chars · Voice: 60 sec)"]
        CORS["CORS Policy\n(Allowed origins only)"]
    end

    subgraph AuthZ["Authentication & Authorization"]
        JWT["JWT Token Verification\n(Every API call)"]
        RLS["Row Level Security\n(User data isolation)"]
        OAUTH["Google OAuth\n(Secure token exchange)"]
    end

    subgraph InputSec["Input Security"]
        IV["Input Validation\n(Dates · Budgets · Destinations)"]
        SAN["Prompt Injection Defense\n(Sanitize before agents)"]
        SCHEMA["Schema Validation\n(MCP arguments)"]
    end

    subgraph ToolSec["Tool Security"]
        AV["Argument Validation\n(Pre-call schema check)"]
        OV["Output Validation\n(Post-call response check)"]
        TO["Timeout Enforcement\n(10 sec per tool)"]
        RET["Retry Limits\n(Max 3 per call)"]
    end

    subgraph OutputSec["Output Security"]
        FG["Factual Grounding\n(Nominatim verification)"]
        BC["Budget Compliance\n(Hard constraint enforcement)"]
        CV["Constraint Verification\n(Dates · travelers · prefs)"]
        NH["No Hallucination Policy\n(Tool output only)"]
    end

    subgraph DataSec["Data Security"]
        ENV["Environment Variables\n(No secrets in code)"]
        ENC["Encrypted at Rest\n(Supabase managed)"]
        TLS["TLS in Transit\n(HTTPS everywhere)"]
    end

    Perimeter --> AuthZ --> InputSec --> ToolSec --> OutputSec
    DataSec -.->|Applies to all layers| Perimeter & AuthZ & InputSec & ToolSec & OutputSec
```

### 9.2 Security Principles

| Layer | Principle | Implementation |
|-------|-----------|----------------|
| **Perimeter** | Defense in depth | Rate limiting + input length limits + CORS policy |
| **Auth** | Zero trust | JWT verified on every request; no implicit trust |
| **Data Isolation** | Least privilege | Supabase RLS ensures users access only their own data |
| **Input** | Never trust user input | Validate dates (parseable), budgets (positive numbers), destinations (non-empty); sanitize against prompt injection |
| **Tools** | Validate both sides | Schema validation on arguments (pre-call) AND responses (post-call) |
| **Output** | Grounded truth only | Every recommendation backed by tool output; Validator checks factual grounding |
| **Secrets** | Never in code | All API keys, credentials via environment variables; `.env` never committed |
| **Transport** | Encrypt everything | TLS/HTTPS for all external API calls and client-server communication |
| **Storage** | Encrypt at rest | Supabase-managed encryption for PostgreSQL data |

### 9.3 Prompt Injection Defenses

| Defense | Description |
|---------|-------------|
| **Input Sanitization** | Strip control characters, escape special tokens before passing to agents |
| **System Prompt Isolation** | Agent system prompts are immutable; user input is isolated in designated variables |
| **Tool Argument Validation** | MCP layer validates tool arguments against strict schemas — blocks malformed calls |
| **Output Grounding** | Validator ensures all output is derived from tool results, not injected instructions |
| **Audit Trail** | Every agent action logged — post-incident investigation always possible |

---

## 10. Error Handling Strategy

### 10.1 Error Handling Architecture

```mermaid
flowchart TD
    ERR["Error Occurs"]
    ERR --> TYPE{"Error\nType?"}

    TYPE -->|"Transient\n(Network timeout, rate limit)"| RETRY["Retry with\nExponential Backoff\n(Max 3 attempts)"]
    RETRY --> RSUCC{"Retry\nSucceeded?"}
    RSUCC -->|Yes| CONTINUE["Continue Pipeline"]
    RSUCC -->|No| FALLBACK

    TYPE -->|"Tool Failure\n(API down, invalid response)"| FALLBACK["Fallback Chain"]
    FALLBACK --> FB1["1. Retry tool call"]
    FB1 --> FB2["2. Fallback search\n(alternative API)"]
    FB2 --> FB3["3. Graceful degradation\n(skip component)"]
    FB3 --> PARTIAL["Partial Result\n+ User Notification"]

    TYPE -->|"Agent Error\n(Hallucination, bad plan)"| REGEN["Self-Correcting Loop\n(Validator → Planner)"]
    REGEN --> RCHECK{"regen_count\n< 3?"}
    RCHECK -->|Yes| REPLAN["Re-plan affected\nsegments"]
    RCHECK -->|No| WARN["Deliver with\nwarnings"]

    TYPE -->|"Critical Failure\n(Auth fail, DB down)"| STOP["Pipeline Stop\n+ Clear Error Message"]
```

### 10.2 Error Categories & Strategies

| Category | Examples | Strategy | User Impact |
|----------|----------|----------|-------------|
| **Transient** | Network timeout, API rate limit, temporary unavailability | Retry with exponential backoff (max 3) | None (invisible to user) |
| **Tool Failure** | AviationStack down, Tavily unreachable, GraphHopper timeout | Fallback chain → graceful degradation → proceed with partial results | Minor — user informed of missing component |
| **Agent Error** | Hallucinated attraction, bad scheduling, budget miscalculation | Validator catches → self-correcting loop (max 3 regen) | None if fixed; warnings if max regen reached |
| **Validation Failure** | Non-existent place, impossible routing, severe budget violation | Reject plan → regeneration with specific feedback | Slightly longer wait (additional regen cycle) |
| **Critical** | Auth failure, database down, LLM provider outage | Pipeline stops; user receives specific error message | Full — user asked to retry later |

### 10.3 Graceful Degradation Rules

| Failure | Degradation Behavior | User Message |
|---------|----------------------|--------------|
| Flight Agent fails | Continue with Hotel, Attraction, Transport; itinerary notes "flights not available" | "We couldn't find flight options right now. The rest of your plan is ready — you can search flights separately." |
| Hotel Agent fails | Continue with other agents; recommend manual hotel search | "Hotel recommendations are temporarily unavailable. We've completed your itinerary — add hotels when ready." |
| All workers fail | Pipeline stops; retain Planner analysis | "We're having trouble connecting to our travel services. Please try again in a few minutes." |
| Voice STT fails | Fallback to text input | "Voice input isn't working right now. Please type your request instead." |

### 10.4 Error Messaging Principles

- ✅ **Specific:** "No flights found for Tokyo on Dec 25–30"
- ❌ **Generic:** "Planning failed"
- ✅ **Actionable:** "Try different dates or a nearby airport"
- ❌ **Blame:** "An error occurred"

---

## 11. Monitoring & Logging Strategy

### 11.1 Observability Architecture

```mermaid
flowchart TD
    subgraph Sources["Log Sources"]
        AG["Agent Actions"]
        TC["MCP Tool Calls"]
        API["API Requests"]
        ERR["Errors & Failures"]
        PERF["Performance Metrics"]
    end

    subgraph Pipeline["Logging Pipeline"]
        TID["Trace ID\nPropagation"]
        SL["Structured Logging\n(JSON format)"]
        AL["Audit Log Table\n(PostgreSQL)"]
    end

    subgraph Metrics["Key Metrics"]
        LAT["Latency\n(per agent, end-to-end)"]
        COST["Cost\n(LLM tokens, API calls)"]
        CACHE["Cache Hit Rate"]
        SUCC["Pipeline Success Rate"]
        REGEN["Regeneration Count"]
        TOOL["Tool Success Rate"]
    end

    subgraph Alerts["Alerting"]
        A1["Latency > 10 sec"]
        A2["Cache hit rate < 40%"]
        A3["Pipeline failure rate > 1%"]
        A4["API rate limit approaching"]
        A5["LLM cost spike"]
    end

    Sources --> TID --> SL --> AL
    AL --> Metrics
    Metrics --> Alerts
```

### 11.2 Structured Audit Log Format

Every agent action produces a structured log entry:

```json
{
  "timestamp": "2026-06-15T14:32:00Z",
  "trace_id": "trip_abc123_run_001",
  "trip_id": "uuid-trip-id",
  "agent": "flight_agent",
  "model": "groq",
  "tool": "aviationstack_search_flights",
  "arguments": { "origin": "JFK", "destination": "NRT", "date": "2026-03-15" },
  "result": { "status": "success", "flights_found": 8 },
  "latency_ms": 850,
  "cost_usd": 0.003,
  "cache_hit": false,
  "step_number": 2,
  "regeneration_count": 0
}
```

### 11.3 Trace ID Propagation

```mermaid
flowchart LR
    REQ["API Request"] -->|"Generate trace_id"| PA["Planner\n(trace: trip_abc_001)"]
    PA --> FA["Flight\n(trace: trip_abc_001)"]
    PA --> HA["Hotel\n(trace: trip_abc_001)"]
    PA --> AA["Attraction\n(trace: trip_abc_001)"]
    PA --> TA["Transport\n(trace: trip_abc_001)"]
    FA & HA & AA & TA --> BA["Budget\n(trace: trip_abc_001)"]
    BA --> IC["Composer\n(trace: trip_abc_001)"]
    IC --> VA["Validator\n(trace: trip_abc_001)"]
```

- Every trip gets a unique `trace_id` at API entry
- All agents, tool calls, and log entries carry the same `trace_id`
- Enables end-to-end tracing of any single request across the entire pipeline

### 11.4 Key Metrics & Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| End-to-end latency (p50) | < 5 sec | > 10 sec |
| End-to-end latency (p95) | < 10 sec | > 15 sec |
| Pipeline success rate | ≥ 99% | < 98% |
| Tool success rate | ≥ 95% | < 90% |
| Cache hit rate | ≥ 40% | < 30% |
| Cost per trip plan | < $0.50 | > $1.00 |
| Self-correcting loop frequency | < 20% of plans | > 40% |
| Mean regeneration cycles | < 1.5 | > 2.5 |

---

## 12. Scalability Strategy

### 12.1 Scalability Architecture

```mermaid
flowchart TD
    subgraph LB["Load Balancer"]
        NX["Nginx / Cloud LB"]
    end

    subgraph AppTier["Application Tier (Horizontally Scalable)"]
        API1["FastAPI Instance 1"]
        API2["FastAPI Instance 2"]
        API3["FastAPI Instance N"]
    end

    subgraph Workers["Agent Workers (Horizontally Scalable)"]
        W1["Worker Pool 1\n(Flight · Hotel)"]
        W2["Worker Pool 2\n(Attraction · Transport)"]
        W3["Worker Pool N"]
    end

    subgraph Cache["Shared Cache"]
        RD["Upstash Redis\n(Managed · Auto-Scale)"]
    end

    subgraph DB["Database"]
        PG["Supabase PostgreSQL\n(Managed · Connection Pooling)"]
    end

    subgraph ExtLLM["LLM Providers"]
        GROQ["Groq Cloud\n(Auto-scaled)"]
        GEM["Gemini API\n(Auto-scaled)"]
    end

    NX --> API1 & API2 & API3
    API1 & API2 & API3 --> Workers
    API1 & API2 & API3 <--> RD
    API1 & API2 & API3 <--> PG
    Workers <--> GROQ & GEM
    Workers <--> RD
```

### 12.2 Scalability Dimensions

| Dimension | Strategy | Mechanism |
|-----------|----------|-----------|
| **API Layer** | Horizontal scaling | Multiple FastAPI instances behind load balancer; stateless design (state in Redis) |
| **Agent Workers** | Horizontal scaling | Worker agents are stateless; state lives in LangGraph State + Redis; any instance can process any request |
| **Database** | Managed scaling | Supabase PostgreSQL with connection pooling (PgBouncer); read replicas for analytics |
| **Cache** | Managed scaling | Upstash Redis with auto-scaling; no infrastructure management |
| **LLM Inference** | Provider-managed | Groq and Gemini Cloud APIs auto-scale; no self-hosted GPU management |
| **MCP Tools** | Rate limit management | Per-API rate limiting at MCP layer; queuing for burst traffic; caching reduces load |
| **Voice Pipeline** | Separate scaling | STT/TTS processing can scale independently of planning pipeline |

### 12.3 Caching Strategy (Latency + Cost Reduction)

| Cache Target | TTL | Impact |
|--------------|-----|--------|
| Flight search results | 1 hour | Avoid repeated AviationStack calls for same route/date |
| Hotel search results | 1 hour | Avoid repeated Tavily calls for same destination |
| Attraction data | 24 hours | Attraction info changes infrequently |
| Geocoding results | 7 days | Coordinates rarely change |
| Route calculations | 24 hours | Routes are stable |
| User session state | Session duration | Fast session restore |
| Agent intermediate results | Session duration | Enable plan iteration without re-running entire pipeline |

### 12.4 Concurrency Model

```
Request 1 ─── [Planner] ──┬── [Flight] ──┐
                           ├── [Hotel]  ──┤
                           ├── [Attract] ─┤── [Budget] → [Composer] → [Validator]
                           └── [Trans]  ──┘

Request 2 ─── [Planner] ──┬── [Flight] ──┐
              (parallel)   ├── [Hotel]  ──┤
                           ├── [Attract] ─┤── [Budget] → [Composer] → [Validator]
                           └── [Trans]  ──┘
```

- Each user request runs as an independent pipeline instance
- Multiple requests execute concurrently (FastAPI async + LangGraph async)
- Worker agents within a single request run in parallel
- No shared mutable state between requests (isolation via trace_id)

---

## 13. Testing & Evaluation Strategy

### 13.1 Testing Strategy

| Test Type | Scope | Tools |
|-----------|-------|-------|
| **Unit Tests** | Individual agent logic, MCP client parsers, budget calculations | pytest |
| **Integration Tests** | Agent-to-agent communication, MCP client → External MCP Server calls, memory operations | pytest + mocks |
| **End-to-End Tests** | Full pipeline: input → plan → PDF → email | pytest + real APIs |
| **Load Tests** | Concurrent users, API rate limit handling | locust / k6 |
| **Voice Tests** | STT accuracy, TTS quality, VAD reliability | Manual + automated |

### 13.2 Golden Travel Request Dataset

Evaluate the system against a curated set of representative travel requests:

| # | Request | Complexity | Key Validation |
|---|---------|------------|----------------|
| 1 | "5-day Japan, Tokyo+Kyoto, $3K, food+temples" | Medium | Multi-city, budget, preferences |
| 2 | "Weekend in Paris, $500, solo" | Low | Simple, tight budget |
| 3 | "2-week Southeast Asia, 4 countries, $5K, family of 4" | High | Multi-country, large group, complex routing |
| 4 | "Ski trip to Swiss Alps, $8K, luxury" | Medium | Seasonal, luxury tier |
| 5 | "Backpacking Central America, 3 weeks, $2K" | High | Low budget, long duration, multiple borders |
| 6 | Repeat user with stored preferences | Medium | Memory recall, preference application |
| 7 | Vague request: "I want to go somewhere warm" | Low | Discovery agent, follow-up questions |
| 8 | Budget-impossible: "$200 for 2-week Europe" | Low | Budget Agent rejection, helpful feedback |

### 13.3 Performance Benchmarks

| Metric | Baseline (Manual Planning) | Target (v1 AI Agent) |
|--------|---------------------------|----------------------|
| Time to complete trip plan | 3–8 hours | < 5 minutes |
| Number of sources consulted | 8–12 websites/apps | Integrated via MCP |
| Budget accuracy (final vs. planned) | ±20–30% variance | ±5% variance |
| Plan iteration time | 1–2 hours per variation | < 30 seconds |
| Personalization application | None (generic recommendations) | 100% preference-aware |
| Voice interaction support | 0% (text-only) | 100% (voice + text) |
| Real-time data freshness | Stale (hours/days old) | Live (API calls) |
| Cost per trip plan (user time value) | $150–$400 | < $5 |
| Plan abandonment rate | ~40–60% (complex trips) | < 10% |

### 13.4 Evaluation Metrics

| Category | Metric | Target |
|----------|--------|--------|
| **Quality** | Constraint satisfaction rate | ≥ 95% |
| **Quality** | Preference alignment score | ≥ 90% |
| **Quality** | Plan completeness (all sections present) | 100% |
| **Quality** | Factual grounding (all places exist) | ≥ 98% |
| **Agents** | Tool selection accuracy | ≥ 90% |
| **Agents** | Tool success rate (non-failure) | ≥ 95% |
| **Agents** | Validation accuracy | ≥ 95% |
| **System** | End-to-end latency (p50) | < 5 seconds |
| **System** | End-to-end latency (p95) | < 10 seconds |
| **System** | Cost per trip plan | < $0.50 |
| **System** | Cache hit rate | ≥ 40% |
| **System** | Pipeline success rate | ≥ 99% |
| **System** | Plan abandonment rate | < 10% |

---

## 14. Ethical & Responsible AI Strategy

### 14.1 Ethical AI Principles

The system is designed with six core ethical AI principles that guide all development, deployment, and operational decisions:

| # | Principle | Description | Implementation |
|---|-----------|-------------|----------------|
| 1 | **Fairness & Non-Discrimination** | Travel recommendations must not discriminate based on protected characteristics | Neutral attraction/restaurant discovery; no demographic-based filtering; diverse option presentation |
| 2 | **Transparency & Explainability** | Users understand how recommendations are generated and can audit the process | Clear agent roles displayed; tool call sources shown; validation feedback visible; PDF includes sourcing |
| 3 | **Privacy & Data Minimization** | Collect only necessary data; protect user information; respect consent | Supabase RLS for data isolation; explicit consent for voice recording; 1-year episodic memory retention; GDPR-compliant data handling |
| 4 | **Accountability & Human Oversight** | AI assists but does not replace human judgment; users retain final control | Editable transcripts; human override on warnings; budget strict mode as user choice; regeneration limit with manual escalation |
| 5 | **Safety & Reliability** | Prevent harm through factual grounding and validation | Nominatim location verification; Validator agent factual checks; no speculative recommendations; graceful degradation on failures |
| 6 | **Environmental Responsibility** | Minimize computational resource consumption | Groq (energy-efficient inference) for speed-critical agents; aggressive caching to reduce API calls; efficient model selection |

### 14.2 Bias Mitigation Strategy

| Bias Type | Risk | Mitigation |
|-----------|------|------------|
| **Location Bias** | Over-recommending popular/western destinations | Diverse attraction discovery; include local gems; user preference-driven (not popularity-driven) |
| **Price Bias** | Only showing luxury options | Multi-tier hotel/flight options; budget-first filtering; explicit budget constraints |
| **Cultural Bias** | Misrepresenting local customs/attractions | Grounded descriptions via Tavily Search; Nominatim verification; avoid stereotypical language |
| **Accessibility Bias** | Ignoring mobility/accessibility needs | Future: accessibility filters; current: explicit user preference capture for mobility needs |
| **Language Bias** | English-only recommendations | Future: multi-language support; current: clear language limitations in UI |

### 14.3 Privacy & Data Protection

```mermaid
flowchart TD
    subgraph DataCollection["Data Collection"]
        VOICE["Voice Audio"]
        TEXT["Text Input"]
        PREFS["User Preferences"]
    end

    subgraph Consent["Consent Layer"]
        C1["Voice Recording Consent"]
        C2["Data Storage Consent"]
        C3["Preference Sharing Consent"]
    end

    subgraph Storage["Secure Storage"]
        RLS["Supabase RLS\n(User Data Isolation)"]
        ENC["Encryption at Rest"]
        RET["1-Year Retention\n(Episodic Memory)"]
    end

    subgraph Access["Access Control"]
        JWT["JWT Authentication"]
        AUD["Audit Logging"]
        DEL["User Data Deletion"]
    end

    VOICE --> C1
    TEXT & PREFS --> C2
    PREFS --> C3
    C1 & C2 & C3 --> Storage
    Storage --> Access
```

**Data Protection Measures:**

| Data Type | Storage | Retention | Access Control | Deletion |
|-----------|---------|-----------|----------------|----------|
| Voice Audio | Temporary (STT processing only) | Deleted immediately after transcription | Not stored | Auto-delete |
| Transcripts | PostgreSQL (chat_messages) | 1 year | User-only via RLS | User-requested deletion |
| User Preferences | Mem0 (long-term) | Until user edits/deletes | User-only | User-requested deletion |
| Episodic Memory | PostgreSQL (episodic_memory) | 1 year auto-expiry | User-only via RLS | Auto-expiry + user deletion |
| Trip Plans | PostgreSQL (trips, itineraries) | Until user deletes | User-only via RLS | User-requested deletion |
| Audit Logs | PostgreSQL (audit_log) | 90 days | Admin-only (for debugging) | Auto-purge |

**Consent Management:**
- Voice recording requires explicit opt-in before microphone access
- Data storage consent shown during onboarding
- Preference sharing opt-in for personalization features
- GDPR-compliant right to data export and deletion

### 14.4 Transparency & Explainability

**User-Facing Transparency:**

| Transparency Feature | Implementation | User Benefit |
|---------------------|----------------|--------------|
| **Agent Role Display** | UI shows which agent is working ("Searching flights…", "Validating plan…") | Understands pipeline progress |
| **Source Attribution** | Each recommendation includes data source (e.g., "Via AviationStack", "Verified via Nominatim") | Trust in factual grounding |
| **Validation Feedback** | Validator issues explained in plain language ("Attraction X is closed on Sundays") | Understands plan quality |
| **Budget Breakdown** | Detailed cost breakdown by category with totals | Clear cost transparency |
| **Preference Application** | UI shows which stored preferences were applied | Awareness of personalization |
| **PDF Sourcing** | Generated PDF includes API source footnotes | Audit trail for offline review |

**Internal Explainability:**

- Every agent decision logged with reasoning trace in audit_log
- Tool call arguments and results recorded for debugging
- Trace ID enables full pipeline reconstruction
- Validation failures include specific issue categories and evidence

### 14.5 Human-in-the-Loop Controls

| Control Point | Human Intervention | Trigger |
|--------------|-------------------|--------|
| **Input Validation** | Editable transcript review | After STT processing |
| **Budget Strictness** | User chooses strict vs. flexible budget mode | During constraint entry |
| **Validation Warnings** | User can override minor validation issues | When Validator flags non-critical issues |
| **Plan Iteration** | User can request manual changes | After plan delivery |
| **Escalation Path** | Human support for unresolved issues | After max regeneration (3 loops) |

### 14.6 Safety & Harm Prevention

**Safety Mechanisms:**

| Risk | Prevention | Detection | Response |
|------|------------|-----------|----------|
| **Non-existent places** | Nominatim verification before recommendation | Validator factual check | Regeneration with corrected data |
| **Dangerous locations** | Travel advisory integration (future) | User warning flag | Explicit user confirmation |
| **Budget overruns** | Gemini arithmetic + strict mode | Budget Agent validation | Auto-optimization or rejection |
| **Impossible routing** | GraphHopper/OSRM validation | Validator routing check | Alternative route suggestion |
| **Closed attractions** | Hours-of-operation checking | Validator timing check | Rescheduling or substitution |
| **Prompt injection** | Input sanitization + tool argument validation | MCP client schema validation | Rejection with error message |

**Content Safety:**
- No generation of illegal or harmful activity recommendations
- No recommendations for restricted areas or prohibited activities
- Respect local laws and cultural norms in suggestions
- Avoid politically sensitive or controversial content

### 14.7 Environmental Impact Mitigation

| Optimization | Environmental Benefit | Implementation |
|-------------|---------------------|----------------|
| **Groq for speed-critical agents** | Energy-efficient inference vs. larger models | Planner, Flight, Hotel, Attraction, Transport, Composer use Groq |
| **Aggressive caching** | Reduces redundant API calls | Redis caching with 1-hour to 7-day TTLs |
| **Model selection** | Right-sized models for tasks | Gemini only for arithmetic/validation (not creative work) |
| **Step limits** | Prevents unnecessary token consumption | Per-agent max steps (2-5) |
| **Parallel execution** | Reduces total wall-clock time | Concurrent worker agents |
| **Efficient batching** | Minimizes API round-trips | Batched MCP tool calls where possible |

**Estimated Carbon Impact:**
- Target: < 0.01 kg CO2e per trip plan
- Achieved via: Groq (low-carbon inference) + caching + efficient architecture
- Monitoring: Track LLM token usage and API call count per trip

### 14.8 Compliance & Governance

**Regulatory Compliance:**

| Regulation | Relevance | Compliance Measures |
|------------|-----------|-------------------|
| **GDPR** | EU user data protection | Right to deletion, data portability, consent management, 1-year retention |
| **CCPA** | California privacy rights | Opt-out of data sale, deletion rights, transparency |
| **AI Act (EU)** | AI system classification | System classified as "limited risk" (transparency obligations only) |
| **COPPA** | Children's online privacy | Age verification required; no data collection from under-13 |

**Internal Governance:**

- **Ethics Review Board**: Quarterly review of AI decisions and user feedback
- **Bias Audits**: Biannual analysis of recommendation patterns for demographic bias
- **Safety Incidents**: Incident logging and review process for safety-related failures
- **Model Documentation**: Model cards for each LLM used (capabilities, limitations, intended use)
- **Version Control**: All agent prompts and schemas versioned for auditability

### 14.9 Continuous Ethical Monitoring

| Monitoring Aspect | Metric | Target | Alert Threshold |
|------------------|--------|--------|----------------|
| **Fairness** | Destination diversity score | ≥ 80% (no single destination > 20%) | < 60% |
| **Transparency** | User understanding survey score | ≥ 4/5 | < 3/5 |
| **Privacy** | Data deletion request fulfillment time | < 24 hours | > 48 hours |
| **Safety** | Non-existent place recommendation rate | 0% | > 0% |
| **Bias** | Demographic parity in recommendations | Within 10% variance | > 20% variance |
| **Environmental** | CO2e per trip plan | < 0.01 kg | > 0.02 kg |

**Feedback Loop:**
- User feedback on recommendation quality and fairness
- Quarterly ethics review with stakeholder input
- Incident-driven policy updates
- Public transparency report (annual)

---

## 15. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| AviationStack API rate limits hit during peak usage | Flight search fails for users | Medium | Redis caching (1-hour TTL), rate limit monitoring, graceful degradation |
| LLM hallucination (non-existent attractions) | User receives incorrect recommendations | Medium | Nominatim/Maps verification in Validator, factual grounding checks |
| Budget calculation errors | User plans exceed budget | Low | Gemini for arithmetic, deterministic budget logic, Validator re-check |
| Voice transcription errors (ASR) | Incorrect trip constraints extracted | Medium | Editable transcript fallback, Planner confirmation of constraints |
| High end-to-end latency (> 10 sec) | Poor user experience | Medium | Parallel execution, caching, streaming first output at 5 sec |
| External MCP server downtime | Entire tool category unavailable | Low | Health checks, circuit breaker, fallback chains, graceful degradation |
| Mem0 stale preferences | Outdated preferences applied | Low | 1-year freshness window, user can override, preferences page for editing |
| Self-correcting loop infinite regen | Pipeline never completes | Low | Hard max of 3 regeneration iterations |
| Prompt injection via user input | Agent executes malicious actions | Low | Input sanitization, tool argument validation, output grounding |
| Cost overrun (LLM API costs) | Exceeds operational budget | Medium | Per-agent step limits, model selection (Groq over Gemini where possible), caching |
| External MCP server API changes | MCP client calls fail silently | Low | Schema validation at MCP client layer, versioned MCP tool schemas, post-call response validation |

---

## 16. Deployment & Execution Strategy

### 15.1 Deployment Architecture

```mermaid
flowchart TD
    subgraph Dev["Development"]
        DC["Docker Compose<br/>(backend + Next.js only)"]
        ENV[".env Config<br/>(Supabase · Upstash · LLM keys)"]
    end

    subgraph CI["CI/CD Pipeline"]
        GH["GitHub Actions"]
        LINT["Lint and Format"]
        TEST["Unit and Integration Tests"]
        BUILD["Docker Build"]
        PUSH["Push to Registry"]
    end

    subgraph Staging["Staging Environment"]
        STG["Staging Deploy<br/>(Same infra as prod)"]
        SMOKE["Smoke Tests<br/>(Golden Dataset subset)"]
    end

    subgraph Prod["Production"]
        LB["Load Balancer"]
        APP["FastAPI Containers<br/>(Auto-scaled)"]
        SUPA["Supabase<br/>(Managed PostgreSQL and Auth)"]
        UPST["Upstash Redis<br/>(Managed Cache)"]
        CDN["Vercel<br/>(Next.js Frontend)"]
    end

    subgraph ExtMCP["External Dependencies"]
        MCPS["External MCP Servers<br/>(Hosted Separately)"]
        LLMS["LLM APIs<br/>(Groq and Gemini)"]
        VOICE["Voice APIs<br/>(ElevenLabs)"]
    end

    APP --> MCPS
    APP --> LLMS
    APP --> VOICE

    DC --> GH
    GH --> LINT
    LINT --> TEST
    TEST --> BUILD
    BUILD --> PUSH
    PUSH --> STG
    STG --> SMOKE
    SMOKE --> LB
    LB --> APP
    APP --> SUPA
    APP --> UPST
    CDN --> LB
```

### 15.2 Environment Configuration

| Environment | Purpose | Data & Cache | When Used |
|-------------|---------|--------------|-----------|
| **Local** | Developer machine (Phases 0–6) | **Docker PostgreSQL** + **Docker Redis** via `docker-compose.yml` | All feature development and testing |
| **Staging** | Pre-production validation | **Supabase** + **Upstash** (managed) | After Phase 7 migration |
| **Production** | Live user-facing system | **Supabase** + **Upstash** + cloud app hosts | After Phase 7 migration |

### 15.2.1 Local → Managed Migration Strategy

```mermaid
flowchart LR
    subgraph Dev["Phases 0–6 — Local"]
        DC["docker-compose.yml"]
        PG["postgres container"]
        RD["redis container"]
        BE["backend"]
        DC --> PG & RD
        BE --> PG & RD
    end

    subgraph Mig["Phase 7 — Migration"]
        M["scripts/migrate_to_managed.py"]
        ENV["APP_ENV=production"]
    end

    subgraph Prod["Staging / Production"]
        SUPA["Supabase PostgreSQL + Auth"]
        UPST["Upstash Redis"]
        DCP["docker-compose.prod.yml\n(backend + frontend only)"]
    end

    Dev --> Mig --> Prod
```

| Phase | Infrastructure | `APP_ENV` | Connection vars |
|-------|----------------|-----------|-----------------|
| 0–6 | Local Postgres + Redis in Docker | `local` | `DATABASE_URL`, `REDIS_URL` |
| 7+ (staging/prod) | Supabase + Upstash | `production` | `SUPABASE_*`, `UPSTASH_*` |

**Why local first, then migrate?**
- Faster iteration with no cloud dependency during Phases 0–6
- Repeatable seeds and integration tests against a known local DB
- Single controlled cutover in Phase 7 before Git push and production deploy
- `docker-compose.yml` **kept** for ongoing local development; production uses `docker-compose.prod.yml` without database containers

**Migration steps (Phase 7 tasks 7.11–7.15):** See [phase-wise-implementationPlan.md §9.1](phase-wise-implementationPlan.md).

### 15.3 Container Architecture

**Local development — `docker-compose.yml`:**

```
docker-compose.yml
├── backend        # FastAPI + LangGraph + Agents  → DATABASE_URL, REDIS_URL
├── frontend       # Next.js dev server
├── postgres       # PostgreSQL 15 (local data store)
└── redis          # Redis 7 (session cache, MCP cache, rate limits)
```

**Production / staging — `docker-compose.prod.yml`:**

```
docker-compose.prod.yml
├── backend        # Connects to Supabase + Upstash via .env.production
└── frontend       # Next.js (or deploy frontend to Vercel separately)

# postgres and redis REMOVED — use managed services
```

**Managed services (production & staging):**
- Supabase (PostgreSQL + Auth) — hosted
- Upstash Redis — hosted
- Groq / Gemini APIs — cloud LLM providers
- ElevenLabs — cloud TTS provider
- **External MCP Servers** — hosted in a separate project; this project connects to them via MCP Clients
  - AviationStack, Tavily Search, GraphHopper/OSRM, Nominatim, Gmail — accessed through external MCP servers

### 15.4 Execution Flow (Runtime)

```mermaid
flowchart LR
    START["User Request"] --> AUTH["Auth Check\n(JWT)"]
    AUTH --> PARSE["Parse Input\n(Voice → STT → Text)"]
    PARSE --> PIPE["LangGraph Pipeline\n(Async Execution)"]
    PIPE --> STREAM["SSE Stream\n(Real-Time Updates)"]
    STREAM --> RENDER["UI Renders\nPlan Progressively"]
    PIPE --> GEN["Generate Outputs\n(PDF · Email · Voice)"]
    GEN --> DELIVER["Deliver to User"]
    PIPE --> LOG["Audit Log\n(PostgreSQL)"]
```

### 15.5 Environment Variables

#### Local development (`APP_ENV=local`)

| Variable | Default (Docker Compose) | Description |
|----------|--------------------------|-------------|
| `APP_ENV` | `local` | Selects local connection profile in `config.py` |
| `DATABASE_URL` | `postgresql://postgres:postgres@postgres:5432/travel_db` | Local PostgreSQL |
| `REDIS_URL` | `redis://redis:6379/0` | Local Redis |
| `SUPABASE_URL` | — | Supabase Auth endpoint (optional in local; required for OAuth testing) |
| `SUPABASE_ANON_KEY` | — | Supabase public key for Next.js auth client |

#### Production / staging (`APP_ENV=production`) — set after Phase 7 migration

| Variable | Service | Description |
|----------|---------|-------------|
| `APP_ENV` | — | `production` or `staging` |
| `SUPABASE_URL` | Supabase | PostgreSQL + Auth endpoint |
| `SUPABASE_ANON_KEY` | Supabase | Public client key |
| `SUPABASE_SERVICE_KEY` | Supabase | Server-side service key |
| `UPSTASH_REDIS_URL` | Upstash | Redis connection URL |
| `UPSTASH_REDIS_TOKEN` | Upstash | Redis auth token |

#### Shared (all environments)
| `GROQ_API_KEY` | Groq | LLM inference API key |
| `GEMINI_API_KEY` | Google | Gemini LLM API key |
| `MEM0_API_KEY` | Mem0 | Long-term memory API key |
| `AVIATIONSTACK_API_KEY` | AviationStack | Flight search API key |
| `TAVILY_API_KEY` | Tavily | Search API key |
| `ELEVENLABS_API_KEY` | ElevenLabs | TTS API key |
| `GMAIL_CLIENT_ID` | Google | Gmail OAuth client ID |
| `GMAIL_CLIENT_SECRET` | Google | Gmail OAuth client secret |
| `NEXT_PUBLIC_API_URL` | Next.js | FastAPI backend URL (browser) |
| `NEXT_PUBLIC_SUPABASE_URL` | Next.js | Supabase project URL (auth client) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Next.js | Supabase anon key (auth client) |

---

## 17. Directory Structure (Final State)

```
Real-Time-Voice-AI-Travel-Planning-Multi-Agent-System/
│
├── 📁 backend/
│   ├── 📁 app/
│   │   ├── main.py                          # FastAPI entry point, middleware, CORS
│   │   ├── config.py                        # Pydantic settings, environment config
│   │   │
│   │   ├── 📁 routers/                      # API route handlers
│   │   │   ├── auth.py                      #   Auth routes (register, login, OAuth)
│   │   │   ├── trips.py                     #   Trip planning routes (plan, followup, status)
│   │   │   ├── itineraries.py               #   Itinerary retrieval and export
│   │   │   ├── profile.py                   #   User profile and preference management
│   │   │   └── health.py                    #   Health check endpoint
│   │   │
│   │   ├── 📁 models/                       # Pydantic schemas & data models
│   │   │   ├── user.py                      #   User, Profile schemas
│   │   │   ├── trip.py                      #   Trip, Constraints, Preferences schemas
│   │   │   ├── itinerary.py                 #   Itinerary, DayPlan, Activity schemas
│   │   │   ├── budget.py                    #   BudgetBreakdown, ComplianceReport schemas
│   │   │   └── agent.py                     #   AgentResponse, ToolResult schemas
│   │   │
│   │   ├── 📁 agents/                       # Agent definitions & prompts
│   │   │   ├── base.py                      #   BaseAgent class (shared behavior)
│   │   │   ├── planner.py                   #   Planner Agent (Manager)
│   │   │   ├── flight.py                    #   Flight Agent (Parallel Worker)
│   │   │   ├── hotel.py                     #   Hotel Agent (Parallel Worker)
│   │   │   ├── attraction.py                #   Attraction Agent (Parallel Worker)
│   │   │   ├── transport.py                 #   Transport Agent (Parallel Worker)
│   │   │   ├── budget.py                    #   Budget Agent (Sequential)
│   │   │   ├── composer.py                  #   Itinerary Composer Agent (Sequential)
│   │   │   └── validator.py                 #   Validator / Critic Agent (Sequential)
│   │   │
│   │   ├── 📁 graph/                        # LangGraph workflow definitions
│   │   │   ├── state.py                     #   TravelPlanState TypedDict
│   │   │   ├── nodes.py                     #   Graph node functions
│   │   │   ├── edges.py                     #   Conditional edge logic
│   │   │   └── workflow.py                  #   StateGraph assembly & compilation
│   │   │
│   │   ├── 📁 mcp_clients/                  # MCP client integrations (connects to External MCP Servers)
│   │   │   ├── base.py                      #   BaseMCPClient (schema validation, retry, rate limiting, cache, audit)
│   │   │   ├── aviationstack.py             #   AviationStack MCP Client
│   │   │   ├── tavily.py                    #   Tavily Search MCP Client
│   │   │   ├── graphhopper.py               #   GraphHopper / OSRM MCP Client
│   │   │   ├── nominatim.py                 #   Nominatim MCP Client
│   │   │   └── gmail.py                     #   Gmail MCP Client
│   │   │
│   │   ├── 📁 memory/                       # Memory layer integrations
│   │   │   ├── mem0_client.py               #   Mem0 long-term preference client
│   │   │   ├── episodic.py                  #   PostgreSQL episodic memory operations
│   │   │   └── session.py                   #   Redis session state management
│   │   │
│   │   ├── 📁 voice/                        # Voice pipeline
│   │   │   ├── stt.py                       #   Groq Whisper API STT integration
│   │   │   ├── tts.py                       #   ElevenLabs TTS integration
│   │   │   └── vad.py                       #   WebRTC VAD configuration
│   │   │
│   │   ├── 📁 services/                     # Business logic services
│   │   │   ├── auth.py                      #   Supabase Auth wrapper
│   │   │   ├── pdf.py                       #   PDF report generator
│   │   │   ├── email.py                     #   Email delivery service
│   │   │   └── streaming.py                 #   SSE event streaming service
│   │   │
│   │   └── 📁 utils/                        # Shared utilities
│   │       ├── logging.py                   #   Structured JSON logging
│   │       ├── tracing.py                   #   Trace ID generation & propagation
│   │       ├── errors.py                    #   Custom exception classes
│   │       └── validators.py                #   Input validation helpers
│   │
│   ├── 📁 tests/
│   │   ├── 📁 unit/                         # Unit tests per component
│   │   ├── 📁 integration/                  # Agent-to-agent, MCP integration tests
│   │   └── 📁 e2e/                          # End-to-end pipeline tests
│   │
│   ├── requirements.txt                     # Python dependencies
│   ├── Dockerfile                           # Backend container definition
│   └── .env.example                         # Environment variable template
│
├── 📁 frontend/                             # Next.js 14+ (App Router, TypeScript)
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── .env.local.example
│   │
│   ├── 📁 src/
│   │   ├── 📁 app/                          # App Router pages
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   ├── globals.css
│   │   │   ├── 📁 (auth)/login/page.tsx
│   │   │   ├── 📁 (auth)/register/page.tsx
│   │   │   ├── dashboard/page.tsx
│   │   │   ├── planner/page.tsx
│   │   │   ├── 📁 itinerary/[id]/page.tsx
│   │   │   └── profile/page.tsx
│   │   │
│   │   ├── 📁 components/                   # React components
│   │   │   ├── VoiceInput.tsx
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── PlanStatus.tsx
│   │   │   ├── ItineraryCard.tsx
│   │   │   ├── BudgetChart.tsx
│   │   │   └── TripCard.tsx
│   │   │
│   │   └── 📁 lib/                          # API, auth, SSE, voice clients
│   │       ├── api.ts
│   │       ├── auth.ts
│   │       ├── sse.ts
│   │       └── voice.ts
│   │
│   └── 📁 public/
│       ├── favicon.ico
│       └── 📁 icons/
│
├── 📁 doc/
│   ├── problemStatement.md
│   ├── enhancedProblemStatement.md
│   ├── AIProductStrategy.md
│   ├── architecture.md                      #   ← This document
│   ├── phase-wise-implementationPlan.md
│   ├── eval.md
│   └── decision.md
│
├── 📁 scripts/
│   ├── _phase_common.py
│   ├── run_phase0.py … run_phase7.py
│   ├── seed_db.py
│   ├── test_golden_dataset.py
│   └── migrate_to_managed.py                # Phase 7: local DB → Supabase, Redis → Upstash
│
├── docker-compose.yml                       # Local dev: backend + frontend + postgres + redis
├── docker-compose.prod.yml                  # Production: backend + frontend only (Phase 7)
├── .env.example                             # APP_ENV=local defaults
├── .env.production.example                  # APP_ENV=production (Supabase + Upstash)
├── .gitignore
├── LICENSE
├── README.md
└── 📁 .github/workflows/                    # Created Phase 7 (final stage)
    └── ci.yml
```

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-06-02 | Initial architecture document — system diagrams, component architecture, data flows, security, monitoring, scalability, deployment, directory structure |
| v1.3 | 2026-06-02 | Local Postgres/Redis in Docker for dev (Phases 0–6); Phase 7 migration to Supabase/Upstash; `docker-compose.prod.yml` |

---

> **Related Documents:**
> - [AIProductStrategy.md](AIProductStrategy.md) — Product strategy, agent job descriptions, PM alignment
> - [enhancedProblemStatement.md](enhancedProblemStatement.md) — Problem statement, functional requirements, technology stack
> - `phase-wise-implementationPlan.md` — Phase-wise implementation plan
