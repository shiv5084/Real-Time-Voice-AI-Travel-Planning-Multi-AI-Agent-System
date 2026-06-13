**AI PRD & Product Strategy Document**
**Agentic Product Specification & System Design Blueprint**
# Real-Time Voice AI Travel Planning Multi-AI Agent System — Product Strategy

Welcome to the Travel AI Agent Design Workspace. As an **AI Product Manager**, the goal of this project is to design, model, and build a high-performing, cost-efficient, and reliable multi-agent travel planning system that converts natural-language requests into actionable, personalized itineraries through voice and text interaction.

We are approaching this design step-by-step, ensuring absolute alignment with product principles (User Trust, Cost Efficiency, Low Latency, Reliability, Personalization, Grounding) and robust engineering practices.

> **Author:** Shiv
> **Date:** 2026-06-02
> **Status:** In Progress
> **Related Docs:** [enhancedProblemStatement.md](enhancedProblemStatement.md)

---

## 🗺️ Project Design Roadmap

- [ ] **Step 1: Defining the Problem Statement**
- [ ] **Step 2: Mapping the User Journey & Defining Agent Touchpoints**
- [ ] **Step 3: The Agent's Job Description**

---

## 📌 Step 1: Defining the Problem Statement

Before we touch agent design, we need crisp clarity on what we're actually solving. Building agents without clear boundaries and baselines leads to automating the wrong things.

### 1.1 Frame the Current State (No Solution Language Yet)

We define the problem in direct user and business terms using the standard PM template:

> **Template:**
> `[User segment] currently [current behavior] when [trigger]. This causes [pain for user] and [cost for business]. Today we solve this by [existing solution] which fails because [gaps].`

#### Applied to Travel Planning Multi-Agent System:

**Travelers and vacation planners** currently **manually research destinations, compare flights and hotels across multiple websites, calculate transportation routes, estimate budgets, and assemble day-by-day itineraries** when **they want to plan a trip to a new destination with specific constraints like budget, dates, travel style, and personal preferences**. This causes **user frustration due to 3–8 hours of fragmented research across 10+ websites, inconsistent information across sources, difficulty staying within budget, lack of personalization beyond generic recommendations, and inability to quickly iterate on plan variations**, and **leads to abandoned trip planning sessions, suboptimal travel experiences, missed opportunities for cost savings, and significant cognitive overhead that discourages frequent travel**. Today, we solve this by **relying on users to manually search Google, TripAdvisor, Booking.com, airline websites, and Google Maps, copy-pasting information into spreadsheets or notes, and mentally coordinating logistics**, which fails because **the process doesn't scale beyond simple trips, produces inconsistent pricing and availability data, delivers no real-time optimization, lacks voice interaction for hands-free planning, and requires re-starting from scratch for every new trip without learning from past preferences**.

---

### 1.2 Quantifying the Problem (The PM's Job)

To measure success and prove value, we establish our performance baselines prior to agent system design:

| Metric | Baseline (Today's Manual Planning) | Target (v1 AI Agent) | Source/Rationale |
| :--- | :--- | :--- | :--- |
| **Time to Complete Trip Plan** | **3–8 hours** | **< 5 minutes** (end-to-end) | Manual research across 10+ sites vs. parallel agent orchestration |
| **Number of Sources Consulted** | **8–12 websites/apps** | **Integrated via MCP APIs** | Tavily, AviationStack, GraphHopper, Nominatim unified |
| **Budget Accuracy (final vs. planned)** | **±20–30% variance** | **±5% variance** | Budget Agent enforces hard checks before delivery |
| **Plan Iteration Time** | **1–2 hours per variation** | **< 30 seconds** | Agent re-runs with new constraints; cached results reused |
| **Personalization Application** | **None (generic recommendations)** | **100% preference-aware** | Mem0 + episodic memory applies food, style, accommodation prefs |
| **Voice Interaction Support** | **0% (text-only)** | **100% (voice + text)** | Groq Whisper API STT + ElevenLabs TTS for summaries |
| **Real-Time Data Freshness** | **Stale (hours/days old)** | **Live (API calls)** | AviationStack, Tavily provide real-time pricing/availability |
| **Transportation Route Accuracy** | **Manual estimation (±30%)** | **GraphHopper/OSRM routing (±5%)** | Professional routing APIs vs. mental math |
| **Multi-City Coordination** | **High error rate (conflicts common)** | **Validator prevents conflicts** | Travel-time validation between cities |
| **Follow-Up Question Efficiency** | **Questionnaire-style (all at once)** | **One-at-a-time, memory-aware** | Travel Discovery Agent asks minimum critical questions |
| **Cost per Trip Plan (user time value)** | **$150–$400** (3–8 hrs × $50/hr) | **<$5** (API costs) | Dramatic user time savings |
| **Plan Abandonment Rate** | **~40–60%** (complex trips) | **< 10%** | Frictionless voice + text + auto-assembly |

---

### 1.3 Scoping the Problem — What's IN vs. OUT

To prevent scope creep and establish a clean boundary for our v1 agent, we explicitly outline what the system will and will not handle.

> [!NOTE]
> *Why this matters for agents:* Every "out of scope" item is an explicit boundary condition — either filtered out early in the pipeline or routed to a structured escape path (log and skip). Naming them now prevents prompt degradation and scope overflow.

*   **In Scope (v1 — Target Flows):**
    *   **Natural-Language Input:** Voice (via Groq Whisper API + WebRTC VAD) and text input for travel requests.
    *   **Travel Discovery:** Agent asks minimum critical follow-up questions (dates, budget, travelers) one at a time, reusing stored preferences.
    *   **Flight Discovery:** Search and validate flights via AviationStack API (MCP-backed).
    *   **Hotel Recommendations:** Search and recommend hotels via Tavily Search API (MCP-backed).
    *   **Attraction Discovery:** Search and validate attractions, restaurants, points of interest via Tavily Search.
    *   **Transportation Planning:** Route calculation and travel-time estimates via GraphHopper/OSRM (routing) and Nominatim (geocoding).
    *   **Budget Enforcement:** Budget Agent aggregates costs, checks compliance, flags over-budget items, suggests adjustments.
    *   **Itinerary Composition:** Itinerary Composer Agent merges all outputs into coherent day-by-day schedule with personalization.
    *   **Validation:** Validator/Critic Agent checks plan quality, budget compliance, conflicts, factual grounding before delivery.
    *   **Personalization:** Mem0 long-term memory for food preferences, travel style, accommodation preferences; PostgreSQL episodic memory for past trips.
    *   **Output Generation:** Structured itinerary (day-by-day), budget breakdown, downloadable PDF report, email delivery.
    *   **Voice Summary:** Concise voice summary of trip (not full itinerary read-aloud) via ElevenLabs TTS.
    *   **Authentication:** Email/password and Google OAuth.
    *   **Multi-Agent Orchestration:** LangGraph-based Manager–Worker pattern with parallel execution (Flight, Hotel, Attraction, Transport) and sequential synthesis (Budget, Composer, Validator).
    *   **Dual-Brain Model Assignment:** Groq for research/synthesis agents; Gemini for budget/validation agents.

*   **Out of Scope (Explicit Handoffs / Boundaries):**
    *   **Real Booking & Payments:** No actual flight/hotel booking or payment processing in v1 (future enhancement).
    *   **Visa & Immigration Processing:** No visa application assistance or documentation generation.
    *   **Travel Insurance:** No insurance recommendation or purchase flows.
    *   **Real-Time Flight Tracking:** No live flight status updates or delay notifications.
    *   **Social Features:** No sharing itineraries with friends, collaborative planning, or social media integration.
    *   **Local Currency Conversion:** No real-time forex rates or multi-currency budgeting.
    *   **Weather Integration:** No weather forecasts or activity recommendations based on conditions.
    *   **Restaurant Reservations:** No actual booking of tables or reservations.
    *   **Event Ticketing:** No concert, show, or event ticket purchases.
    *   **Multi-Language Support:** English-only in v1; no translation for non-English destinations.
    *   **Offline Mode:** Requires internet connectivity for all API calls.
    *   **AR/VR Experiences:** No augmented or virtual reality destination previews.
    *   **Group Travel Splitting:** No complex bill splitting or group coordination features.
    *   **Travel Insurance Claims:** No post-trip claim processing.
    *   **Loyalty Program Integration:** No airline/hotel loyalty point redemption or tracking.

---

### 1.4 Define Success Metrics

Our success definition spans three operational dimensions:

1.  **User Outcome (Traveler):** *"I speak or type my trip idea, and within 5 minutes I have a complete, personalized itinerary that respects my budget, dates, and preferences. The plan includes real flights and hotels I can actually book, accurate transportation routes, and a downloadable PDF I can share. I can ask follow-up questions and iterate instantly without starting over."*
2.  **Business Outcome (Travel Platform):** *"Users complete trip planning at 5–10x the rate of manual methods, with higher satisfaction scores due to personalization and voice interaction. The system scales to handle complex multi-city trips without human intervention, reducing support burden and increasing conversion to actual bookings."*
3.  **Agent-Specific Outcome (Pipeline Engineering):** *"The LangGraph multi-agent pipeline completes end-to-end — input → discovery → planning → validation → delivery — with ≥ 99% success rate. Parallel worker agents (Flight, Hotel, Attraction, Transport) execute concurrently to achieve < 5 second latency. The Budget Agent and Validator enforce hard constraints before any user-facing output. All agent actions are logged with trace IDs for observability and debugging."*

---

### 1.5 The "Why an Agent?" Gut Check

Before building, we verify why a standard travel booking website, simple chatbot, or static itinerary template is insufficient, and why a **Multi-Agent LangGraph-Orchestrated System** is strictly required:

1.  **Complex Multi-Dimensional Optimization:**
    *   *Problem:* Travel planning requires simultaneous optimization across budget, dates, preferences, geography, transportation, and timing — a constraint satisfaction problem that defies simple rule-based approaches.
    *   *Example:* *"Plan a 5-day Japan trip. Tokyo + Kyoto. $3,000 budget. Love food and temples, hate crowds. Prefer budget hotels."*
    *   *Simple Search Engine:* ❌ Fails — can't balance budget vs. hotel quality vs. crowd timing vs. inter-city travel time.
    *   *Multi-Agent System:* ✅ Succeeds — Planner delegates to parallel workers (Flight, Hotel, Attraction, Transport), Budget Agent enforces $3,000 constraint, Composer optimizes day-by-day schedule, Validator ensures no conflicts.

2.  **Better User Experience — Three Measurable CX Wins:**
    *   **Voice-First Interaction:** Plan trips hands-free while driving, cooking, or multitasking. Editable transcript fallback for precision.
    *   **Zero Research Friction:** No tab-switching between 10+ websites. All data unified through MCP APIs.
    *   **Instant Iteration:** Change budget from $3,000 to $2,500 → agent re-runs in 30 seconds with new options. Manual replanning takes hours.

3.  **Multi-System Orchestration — The Real Unlock:**
    *   *Key Distinction:* Websites display options; Agents orchestrate outcomes.
    *   The system executes end-to-end across seven distinct systems in a single pipeline run:
        *   *AviationStack API (via MCP)* — Flight discovery and pricing
        *   *Tavily Search API (via MCP)* — Hotel and attraction research
        *   *GraphHopper/OSRM (via MCP)* — Transportation routing and timing
        *   *Nominatim (via MCP)* — Geocoding and location validation
        *   *Mem0* — Long-term preference memory
        *   *Supabase PostgreSQL* — Episodic memory and user data
        *   *Gmail API* — Itinerary delivery
    *   A manual workflow requires a human to navigate each system sequentially over 3–8 hours. The agent does the thing — end-to-end — in under 5 minutes.

4.  **Scale Across Trip Complexity Without Maintenance Cost:**
    *   One agent system generalizes across:
        *   **Trip complexity variance** — Weekend getaway vs. 2-week multi-country tour
        *   **Budget variance** — $500 backpacking vs. $10,000 luxury
        *   **Traveler count variance** — Solo trip vs. family of 5
        *   **Preference variance** — Foodie vs. adventure vs. cultural traveler
    *   Building rule-based coverage for this matrix is impossible. The agent absorbs variance through LLM reasoning and memory.

5.  **Long-Tail Preference Handling:**
    *   Most travelers have standard preferences (budget hotels, popular attractions). The long tail includes niche needs: gluten-free restaurants, wheelchair accessibility, pet-friendly hotels, specific airline alliances.
    *   Mem0 long-term memory captures these preferences and applies them automatically. The Budget Agent and Validator ensure even niche preferences don't violate hard constraints.

6.  **Continuous Improvement Loop:**
    *   Every pipeline run produces structured, machine-readable artefacts (audit logs with trace IDs, agent actions, tool results, latency, cost). These can be mined to:
        *   Identify new preference patterns to improve personalization
        *   Detect tool failure patterns (e.g., AviationStack rate limits)
        *   Optimize agent step limits and caching strategies
        *   Improve validation rules with real production data
    *   **A travel website gives you a booking page. An agent gives you a dataset.** That compounding advantage enables continuous UX improvement without re-engineering.

---

### 💬 PM Alignment: Key Design Questions for Step 1

To finalise Step 1, please provide feedback on these key baseline assumptions:

1. **Target Latency:** Tiered latency targets:
   - **< 1–2 sec** → UI response starts (streaming begins)
   - **< 5 sec** → first useful output (plan skeleton / partial itinerary)
   - **< 10 sec** → full enriched itinerary (hotels, routes, activities)
2. **Voice Summary Length:** **30–45 seconds** for high-level overview Quick Brief (default)
3. **Budget Agent Strictness:**The Budget Agent should regenerate or optimize automatically **Respect user preference**
4. **Memory Freshness:** Keep **1 year** for episodic memory (past trips)

> **Step 1 Status:** ✅ **COMPLETE** — All baseline assumptions finalized with PM feedback.

---

## 📌 Step 2: Mapping the User Journey & Defining Agent Touchpoints

This is where most PMs jump straight to "the pipeline will have these nodes." Wrong. First map the **human journey as it exists today**, then decide exactly where the agent shows up. The journey reveals the agent's job — not the other way around.

---

### 2.1 Map the Current-State Journey (No Agent Yet)

Pick one flow at a time. The travel planning pipeline has one primary flow: **the end-to-end trip planning cycle**. Map it from the moment a user has a trip idea to the moment they have a bookable itinerary. Do not jump to the agent.

**Current-state journey: Trip Planning (Manual):**

| # | Step | User Does | System / Human Involved | Pain Points | Time Spent |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Trip Idea** | Has a vague idea: *"I want to visit Japan"* | None — mental trigger | No structured starting point; unclear what information is needed | 0 min |
| 2 | **Destination Research** | Opens Google, TripAdvisor, blogs; reads about destinations | Google, TripAdvisor, Wikivoyage | Information overload; inconsistent quality; no personalization | 30–60 min |
| 3 | **Date Selection** | Checks calendar; considers work, holidays, weather | Calendar apps, weather sites | No optimization for best travel dates; price visibility missing | 15–30 min |
| 4 | **Budget Estimation** | Rough mental math or spreadsheet; no real pricing | Spreadsheets, mental math | Highly inaccurate; doesn't account for hidden costs | 20–40 min |
| 5 | **Flight Search** | Opens airline websites, Google Flights, Skyscanner; compares options | Multiple airline sites, Google Flights, Skyscanner | Tab-switching fatigue; inconsistent pricing; no integration with other plans | 45–90 min |
| 6 | **Hotel Search** | Opens Booking.com, Hotels.com, Airbnb; filters by location, price | Multiple hotel booking sites | No context from flight search; doesn't consider transportation to attractions | 30–60 min |
| 7 | **Attraction Research** | Google Maps, TripAdvisor, blogs; lists places to visit | Google Maps, TripAdvisor,Wikivoyage | No scheduling logic; doesn't account for travel time between locations | 30–60 min |
| 8 | **Transportation Planning** | Manually calculates routes between cities and local transit | Google Maps, transit apps | Complex multi-modal routing; no integration with accommodation/attractions | 30–45 min |
| 9 | **Itinerary Assembly** | Copy-pastes information into Word/Google Docs; creates day-by-day schedule | Word, Google Docs, spreadsheets | Manual formatting; no conflict detection; difficult to iterate | 45–90 min |
| 10 | **Budget Validation** | Adds up costs manually; realizes over budget; restarts search | Spreadsheets, calculator | Late discovery of budget violations; painful iteration loop | 20–40 min |
| 11 | **Preference Application** | Mentally tries to remember past trips; applies generic filters | Human memory | No systematic personalization; preferences forgotten or misapplied | 10–20 min |
| 12 | **Final Review & Booking** | Reviews assembled plan; opens each booking site separately | Multiple booking sites | No unified booking; risk of inconsistencies; high cognitive load | 30–60 min |

> [!NOTE]
> **Total Time:** 5–8 hours for a single trip. Steps 5–9 consume 60% of time and produce the most variable output. These are the agent's primary targets.

---

### 2.2 Identify the "Agent-Shaped" Steps

Now overlay where the agent uniquely adds value. Not every step is agent territory. Use this filter:

| Question | If Yes → |
| :--- | :--- |
| Does it require understanding messy, unstructured input? | **Agent** |
| Does it require multi-system action across APIs? | **Agent** |
| Does it require judgment within a defined policy/rule set? | **Agent (with guardrails)** |
| Does it require human creativity, legal sign-off, or stakeholder trust? | **Human** |
| Is it a deterministic data movement step (load CSV, filter dates)? | **Script / Pipeline node — not agentic** |

**Applied to the travel planning pipeline:**

| Step | Agent? | Why | LangGraph Node |
| :--- | :--- | :--- | :--- |
| 1. Trip Idea | **No — user provides** | User initiates with voice/text; agent receives as input | User input → Planner Agent |
| 2. Destination Research | **Agent — core value** | LLM understands vague requests; Tavily Search provides real-time data | Planner Agent + Tavily MCP |
| 3. Date Selection | **Agent + Human** | Agent suggests optimal dates based on price/weather; human finalizes | Planner Agent + AviationStack |
| 4. Budget Estimation | **Agent — core value** | Real-time pricing from APIs; accurate cost aggregation | Budget Agent |
| 5. Flight Search | **Agent — replaces manual search** | AviationStack API provides comprehensive flight data; no tab-switching | Flight Agent (parallel worker) |
| 6. Hotel Search | **Agent — replaces manual search** | Tavily Search provides hotel options with context from other agents | Hotel Agent (parallel worker) |
| 7. Attraction Research | **Agent — replaces manual search** | Tavily Search discovers attractions; validates existence via Maps | Attraction Agent (parallel worker) |
| 8. Transportation Planning | **Agent — core value** | GraphHopper/OSRM provides professional routing; integrates with hotels/attractions | Transport Agent (parallel worker) |
| 9. Itinerary Assembly | **Agent — core value** | Itinerary Composer merges all outputs; applies personalization; creates schedule | Itinerary Composer Agent |
| 10. Budget Validation | **Agent — core value** | Budget Agent enforces constraints; warns on violations; suggests adjustments | Budget Agent (sequential) |
| 11. Preference Application | **Agent — core value** | Mem0 + episodic memory automatically applies stored preferences | All agents (via memory layer) |
| 12. Final Review & Booking | **Agent → Human hand-off** | Agent provides validated plan; human reviews and books (v1) | Validator Agent + human |

> [!NOTE]
> **Steps 5–9 are where the agent earns its keep.** Parallel worker agents (Flight, Hotel, Attraction, Transport) execute concurrently to reduce latency. The sequential synthesis (Budget, Composer, Validator) ensures quality and constraint compliance.

---

### 2.3 Define Agent Touchpoints (Triggers + Entry Surfaces)

Where and how does the pipeline actually start? PMs often forget that the trigger mechanism is a design choice that affects reliability, latency, and user experience.

| Touchpoint | How It Works | Pros | Cons | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **Web Interface (Voice + Text)** | User speaks or types trip idea on web app; FastAPI backend triggers LangGraph pipeline | Natural interaction; accessible to all users; supports both voice and text | Requires browser; depends on internet connectivity | ✅ **Primary — Start here (v1)** |
| **Mobile App (Voice + Text)** | Native iOS/Android app with voice/text input; same backend as web | Best mobile UX; push notifications for plan delivery | Requires native development; higher maintenance | 🔲 **v2 — Future** |
| **API Integration** | Third-party apps call REST API to trigger planning | Enables partnerships; scalable integration | Requires API management; authentication complexity | 🔲 **v2 — Future** |
| **Slack / Teams Bot** | `/plan-trip` slash command triggers planning workflow | Meets users where they work; good for business travel | Requires bot setup; OAuth integration | 🔲 **v2 — Future** |
| **Email Trigger** | User emails trip idea to dedicated address; parser extracts and triggers pipeline | Familiar interface; async workflow | Latency higher; parsing complexity | 🔲 **v2 — Future** |

> [!NOTE]
> **Pick one primary touchpoint for v1.** The web interface with voice + text is the correct default — it provides the most natural interaction model while leveraging the full voice capability. Mobile app and integrations can follow in v2.

---

### 2.4 Define the Handoff Design (This Is Critical)

Every agent pipeline needs **three exits mapped from day one**. For a travel planning system, "handoff" means: what happens when the agent can't complete the plan cleanly?

**Exit 1 — Happy Path (Pipeline Completes Successfully):**
- All agents complete successfully (Planner → Workers → Budget → Composer → Validator)
- Validator approves plan with no critical issues
- System generates structured itinerary, budget breakdown, PDF report
- Email sent to user with itinerary and download link
- Voice summary generated (30–45 sec Quick Brief)
- **Human role:** Review plan, optionally iterate with follow-up questions, proceed to booking

**Exit 2 — Soft Failure (Budget Violation or Minor Issues):**
- Budget Agent flags plan exceeds budget (unless strict constraint set)
- Validator detects minor issues (e.g., tight timing between activities)
- Pipeline proceeds with warnings; user sees flagged issues with suggestions
- **Human role:** Review warnings, accept plan or request adjustments

**Exit 3 — Hard Failure (Critical Issues or Tool Down):**
- Critical validation failure (e.g., non-existent destination, impossible routing)
- Tool failure (AviationStack down, Tavily unreachable, GraphHopper timeout)
- Pipeline stops; partial results retained (e.g., flights found but hotels failed)
- User receives clear error message with specific failure reason
- **Human role:** Retry with modified request, or fallback to manual planning

**Operator Escape Hatches (Always Available):**

| Flag | Effect |
| :--- | :--- |
| `--dry-run` | Pipeline runs all agents but stops before final delivery; generates preview only |
| `--skip-validation` | Bypasses Validator Agent (not recommended for production) |
| `--strict-budget` | Budget Agent hard-rejects any plan exceeding budget (override default warn behavior) |
| `--max-workers N` | Override default parallel worker count for debugging |
| `--verbose` | Detailed logging of all agent actions, tool calls, and intermediate states |

> [!IMPORTANT]
> **PM Rule:** If a user cannot understand why their plan failed or how to fix it, the handoff design is insufficient. Error messages must be specific (e.g., "No flights found for Tokyo on Dec 25–30" not "Planning failed").

---

### 2.5 Define the Future-State Journey (With Agent)

Now redraw the journey with the agent in place. This is the artifact you hand to engineering and design.

**Future-state journey: Trip Planning (Agentic Pipeline):**

| # | Step | User Does | Agent / Node Does | Time | Exit Risk |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Trip Idea Input** | Speaks or types: *"Plan a 5-day Japan trip. Tokyo + Kyoto. $3,000 budget. Love food and temples, hate crowds."* | **Planner Agent** receives input; applies Mem0 preferences; identifies missing info | < 1 sec (streaming starts) | Low — input validation |
| 2 | **Travel Discovery** | Nothing | **Planner Agent** asks minimum critical questions one at a time (dates, travelers); reuses stored preferences | 10–30 sec interaction | Low — memory-aware questioning |
| 3 | **Parallel Research** | Nothing | **Planner Agent** delegates to parallel workers: **Flight Agent** (AviationStack), **Hotel Agent** (Tavily), **Attraction Agent** (Tavily), **Transport Agent** (GraphHopper/OSRM) | 2–4 sec (parallel execution) | Medium — API rate limits |
| 4 | **Budget Aggregation** | Nothing | **Budget Agent** aggregates costs from all workers; checks against $3,000 constraint; flags violations | < 1 sec | Low — deterministic arithmetic |
| 5 | **Itinerary Composition** | Nothing | **Itinerary Composer Agent** merges worker outputs; applies personalization (food, crowd-avoidance); creates day-by-day schedule | 1–2 sec | Low-Medium — LLM variance |
| 6 | **Validation** | Nothing | **Validator Agent** checks plan quality, budget compliance, conflicts (e.g., Tokyo→Kyoto same morning), factual grounding (places exist on Maps) | 1–2 sec | Medium — validation strictness |
| 7 | **Output Generation** | Nothing | System generates structured itinerary (Markdown), budget breakdown, downloadable PDF, email draft | < 1 sec | Low |
| 8 | **Voice Summary** | Nothing | **ElevenLabs TTS** generates 30–45 sec Quick Brief audio summary | < 1 sec generation | Low |
| 9 | **Delivery** | Nothing | Email sent with itinerary + PDF + voice summary link; web UI displays full plan | < 1 sec | Low |
| 10 | **User Review** | Reviews plan; asks follow-up if needed | **Planner Agent** handles follow-up; re-runs relevant agents with new constraints | 30 sec – 2 min | Low |
| 11 | **Booking (v1)** | Clicks links to book flights/hotels manually | Nothing — agent provides booking-ready plan | 5–10 min | None — intentional human gate |
| 12 | **Exception: Budget Violation** | Reviews warning; accepts or requests adjustment | **Budget Agent** suggests alternatives (different dates, different hotels) | < 30 sec | Controlled |
| 13 | **Exception: Tool Failure** | Sees error message; retries with modified request | System provides specific error (e.g., "No flights available for selected dates") | < 5 sec | Controlled |

> [!NOTE]
> **Total Time:** < 10 seconds for full enriched itinerary (vs. 5–8 hours manual). Streaming begins at 1–2 seconds with plan skeleton. Parallel execution reduces latency by 4–5x vs sequential.

---

### 💬 PM Alignment: Key Design Questions for Step 2

To finalise Step 2, please provide feedback on these key design decisions:

1. **Web Interface Priority:** **Desktop Web First with Responsive Design** that should support both desktop and mobile
2. **Follow-Up Question Depth:** Keep **2–3 questions maximum** at this stage (dates, budget, travelers)
3. **Voice Summary Trigger:** **User-opt-in only** (button to "Listen to Summary") only in voice mode toggle button

> **Step 2 Status:** ✅ **COMPLETE** — All design decisions finalized with PM feedback.

---

## 📌 Step 3: The Agent's Job Description

Now that we understand the problem and the user journey, we define what each agent actually does. This is not technical implementation — it's a clear, human-readable job description for each agent role. Engineers will use these to build prompts, tool schemas, and state management.

---

### 3.1 Agent Overview

The system uses a **Manager–Worker pattern with Sequential Synthesis**:

```
User Input → Planner Agent → Parallel Workers (Flight, Hotel, Attraction, Transport)
                                      ↓
                              Budget Agent (Sequential)
                                      ↓
                          Itinerary Composer Agent (Sequential)
                                      ↓
                              Validator Agent (Sequential)
                                      ↓
                              Final Travel Plan
```

---

### 3.2 Planner Agent (Manager)

**Role:** The central coordinator that understands user intent, extracts constraints, delegates tasks, and orchestrates the entire planning workflow.

**Responsibilities:**
- Parse user input (voice or text) to understand trip intent
- Extract explicit constraints (destination, dates, budget, travelers)
- Apply Mem0 long-term memory to retrieve stored preferences
- Identify missing critical information and ask follow-up questions (one at a time)
- Create execution plan and delegate to parallel worker agents
- Coordinate between parallel and sequential phases
- Handle user follow-up questions and plan iterations

**Inputs:**
- User trip request (voice transcript or text)
- Mem0 preference profile (food, travel style, accommodation, transport)
- PostgreSQL episodic memory (past trips)

**Outputs:**
- Structured trip request with all constraints
- Delegation plan for worker agents
- Follow-up questions (if information missing)

**Tools (via MCP):**
- Tavily Search (destination research, general information)
- Mem0 (preference retrieval)
- PostgreSQL (episodic memory access)

**Model:** Groq (fast, cost-efficient for intent parsing and coordination)

**Key Behaviors:**
- Ask minimum critical questions (dates, budget, travelers) — max 2–3 questions
- Reuse stored preferences to avoid re-asking known information
- Stop asking when sufficient information exists for initial plan
- Allow user to override stored preferences

---

### 3.3 Flight Agent (Parallel Worker)

**Role:** Researches and validates flight options based on user constraints.

**Responsibilities:**
- Search for flights matching origin, destination, dates, and traveler count
- Filter by price, duration, airline preferences (from memory)
- Validate flight availability and pricing
- Return top 3–5 flight options with key details (price, duration, departure/arrival times)
- Handle no-results scenarios with alternative suggestions

**Inputs:**
- Origin and destination (from Planner)
- Travel dates (from Planner)
- Number of travelers (from Planner)
- Budget constraint (from Planner)
- Airline preferences (from Mem0)

**Outputs:**
- List of flight options with pricing, timing, and booking URLs
- Total estimated flight cost for budget aggregation

**Tools (via MCP):**
- AviationStack API (flight search and pricing)

**Model:** Groq (fast research and option generation)

**Key Behaviors:**
- Prioritize direct flights when available
- Consider layover duration and total travel time
- Respect budget constraint in initial filtering
- Provide alternatives if no exact matches found

---

### 3.4 Hotel Agent (Parallel Worker)

**Role:** Researches and recommends hotel options based on location, budget, and preferences.

**Responsibilities:**
- Search for hotels in target destinations
- Filter by location (proximity to attractions/transport), price, amenities
- Apply accommodation preferences from Mem0 (budget vs. luxury, specific amenities)
- Validate hotel availability and pricing
- Return top 3–5 hotel options with key details
- Consider transportation access to planned attractions

**Inputs:**
- Destinations (from Planner)
- Travel dates (from Planner)
- Budget allocation for accommodation (from Planner)
- Accommodation preferences (from Mem0)

**Outputs:**
- List of hotel options with pricing, location, amenities, and booking URLs
- Total estimated accommodation cost for budget aggregation

**Tools (via MCP):**
- Tavily Search (hotel research and discovery)

**Model:** Groq (fast research and option generation)

**Key Behaviors:**
- Prioritize hotels near planned attractions or transit hubs
- Balance price vs. quality based on user budget
- Consider crowd-avoidance preferences (e.g., quieter neighborhoods)
- Provide alternatives if no exact matches found

---

### 3.5 Attraction Agent (Parallel Worker)

**Role:** Discovers and validates attractions, restaurants, and points of interest based on user interests.

**Responsibilities:**
- Search for attractions matching user interests (food, temples, museums, etc.)
- Validate attraction existence and current status (open/closed, seasonal)
- Filter by crowd tolerance (avoid crowded venues if user prefers)
- Consider travel time between attractions
- Return top 5–10 attractions with descriptions, timing, and costs
- Include restaurant recommendations based on food preferences

**Inputs:**
- Destinations (from Planner)
- User interests (from Planner + Mem0)
- Crowd tolerance (from Mem0)
- Food preferences (from Mem0)

**Outputs:**
- List of attractions with descriptions, opening hours, entry fees
- Restaurant recommendations with cuisine types and price ranges
- Estimated activity costs for budget aggregation

**Tools (via MCP):**
- Tavily Search (attraction and restaurant discovery)
- Nominatim (geocoding and location validation)

**Model:** Groq (fast research and option generation)

**Key Behaviors:**
- Prioritize attractions aligned with stated interests
- Consider crowd timing (e.g., visit popular sites early morning)
- Validate that attractions actually exist ( Maps verification)
- Include mix of must-see and hidden gems

---

### 3.6 Transport Agent (Parallel Worker)

**Role:** Plans transportation routes between cities and within destinations.

**Responsibilities:**
- Calculate inter-city transportation options (flights, trains, buses)
- Plan local transportation routes (public transit, taxi, walking)
- Estimate travel times and costs for all segments
- Validate route feasibility and timing
- Return optimized transportation plan with alternatives

**Inputs:**
- Cities and attractions (from Planner + Attraction Agent)
- Travel dates (from Planner)
- Transportation preferences (from Mem0)

**Outputs:**
- Inter-city transportation options with pricing and timing
- Local transportation routes between attractions
- Total estimated transport cost for budget aggregation

**Tools (via MCP):**
- GraphHopper / OSRM (routing and travel-time calculation)
- Nominatim (geocoding for route planning)

**Model:** Groq (fast research and route generation)

**Key Behaviors:**
- Optimize for time vs. cost based on user preferences
- Consider realistic travel times (not just distance)
- Provide multiple options (fastest, cheapest, most convenient)
- Account for transportation schedules and frequency

---

### 3.7 Budget Agent (Sequential)

**Role:** Aggregates costs from all worker agents, validates budget compliance, and enforces constraints.

**Responsibilities:**
- Aggregate estimated costs from Flight, Hotel, Attraction, and Transport agents
- Compare total against user budget constraint
- Flag over-budget items and suggest adjustments
- If budget exceeded, regenerate or optimize plan automatically while respecting user preference
- Provide detailed budget breakdown by category
- Emit budget compliance report for downstream agents

**Inputs:**
- Flight costs (from Flight Agent)
- Hotel costs (from Hotel Agent)
- Activity costs (from Attraction Agent)
- Transport costs (from Transport Agent)
- User budget constraint (from Planner)
- Strict budget flag (if user set hard constraint)

**Outputs:**
- Total estimated trip cost
- Budget compliance status (within budget, warning, over budget)
- Suggested adjustments if over budget
- Detailed budget breakdown by category

**Tools (via MCP):**
- None (deterministic arithmetic and logic)

**Model:** Gemini (stronger structured reasoning for arithmetic and compliance)

**Key Behaviors:**
- **Never exceed the budget** — optimize and regenerate plan automatically if needed
- Prioritize high-impact adjustments (e.g., change hotel vs. skip attraction)
- Provide transparent cost breakdown
- Warn with optimization suggestions before hard-rejecting (unless strict constraint set)

---

### 3.8 Itinerary Composer Agent (Sequential)

**Role:** Merges all worker outputs and budget report into a coherent, personalized day-by-day itinerary.

**Responsibilities:**
- Merge flight, hotel, attraction, and transport outputs
- Apply personalization logic (food preferences, crowd avoidance, travel style)
- Create day-by-day schedule with realistic timing
- Optimize for travel time between locations
- Apply crowd-timing preferences (e.g., popular sites early morning)
- Ensure logical flow (e.g., group nearby activities)
- Produce structured draft itinerary for validation

**Inputs:**
- Flight options (from Flight Agent)
- Hotel options (from Hotel Agent)
- Attractions and restaurants (from Attraction Agent)
- Transportation routes (from Transport Agent)
- Budget compliance report (from Budget Agent)
- User preferences (from Mem0)

**Outputs:**
- Day-by-day itinerary with timing, locations, and activities
- Hotel and flight recommendations integrated into schedule
- Transportation plan between all locations
- Personalization notes (e.g., "Early morning visit to avoid crowds")

**Tools (via MCP):**
- None (synthesis and scheduling logic)

**Model:** Groq (creative synthesis and scheduling)

**Key Behaviors:**
- Group activities by geographic proximity
- Account for realistic travel time and buffer time
- Apply crowd-avoidance timing strategies
- Balance must-see attractions with relaxation time
- Ensure meal times are scheduled appropriately

---

### 3.9 Validator / Critic Agent (Sequential)

**Role:** Validates the composed itinerary for quality, completeness, and factual grounding before delivery to user.

**Responsibilities:**
- Validate overall plan quality and completeness
- Re-check budget compliance
- Detect conflicts (e.g., overlapping cities same morning, impossible timing)
- Ensure factual grounding (places exist on Maps, flights are bookable)
- Validate against user constraints and preferences
- Approve, reject, or request revision before delivery
- Provide specific feedback on any issues found
- **Trigger self-correcting loop**: If issues found, signal Planner Agent to regenerate plan (max 3 iterations)

**Inputs:**
- Composed itinerary (from Itinerary Composer)
- Budget compliance report (from Budget Agent)
- User constraints (from Planner)
- User preferences (from Mem0)

**Outputs:**
- Validation status (approved, needs revision, rejected)
- Specific issues found (if any)
- Suggested revisions (if needed)
- Final approved itinerary (if approved)

**Tools (via MCP):**
- Nominatim (location validation)
- Maps verification (factual grounding check)

**Model:** Gemini (stronger structured reasoning for critique and validation)

**Key Behaviors:**
- Be thorough but not overly pedantic
- Provide specific, actionable feedback
- Distinguish between critical issues (impossible routing) and minor issues (tight timing)
- Allow human override for edge cases
- Log all validation decisions for observability

---

### 3.10 Agent Communication Protocols

**State Sharing:**
- All agents share a common LangGraph State object
- State includes: user request, constraints, preferences, intermediate results, validation status
- Parallel workers write to independent state keys to avoid conflicts
- Sequential agents read from and write to shared state

**Handoff Signals:**
- Planner signals workers when delegation is ready
- Workers signal Budget Agent when all parallel tasks complete
- Budget Agent signals Composer when budget is validated
- Composer signals Validator when itinerary is composed
- Validator signals delivery system when plan is approved
- **Self-Correcting Loop:** Validator signals Planner to regenerate if issues found (max 3 iterations)

**Error Propagation:**
- Each agent reports errors with specific context
- Parallel worker failures don't block other workers (graceful degradation)
- Sequential agents stop on critical failures
- All errors are logged with trace IDs

---

### 3.11 Agent Tool Access Patterns

**MCP Tool Layer:**
- All external API access goes through MCP servers
- Consistent error handling and retry logic at MCP layer
- Rate limiting and caching managed centrally
- Tool schemas standardized across agents

**Tool Assignment:**
- AviationStack → Flight Agent only
- Tavily Search → Planner, Hotel, Attraction Agents
- GraphHopper/OSRM → Transport Agent only
- Nominatim → Attraction, Transport, Validator Agents
- Mem0 → Planner Agent (preference retrieval)
- PostgreSQL → Planner Agent (episodic memory)
- Gmail → Delivery system (not an agent)

---

### 3.12 Agent Performance Expectations

**Latency Targets:**
- Planner Agent: < 1 sec (intent parsing + memory lookup)
- Parallel Workers (Flight, Hotel, Attraction, Transport): 2–4 sec total (concurrent)
- Budget Agent: < 1 sec (deterministic arithmetic)
- Itinerary Composer: 1–2 sec (scheduling logic)
- Validator Agent: 1–2 sec (validation checks)

**Quality Targets:**
- Intent understanding accuracy: ≥ 95%
- Tool selection accuracy: ≥ 90%
- Validation accuracy: ≥ 95%
- Plan accuracy (factual grounding): ≥ 98%

**Failure Handling:**
- Each agent has max retry count (default: 3)
- Graceful degradation on partial failures
- Fallback to simpler strategies on complex failures
- All failures logged with context

---

### 3.13 Self-Correcting Loop

**Purpose:** Enable automatic plan improvement when Validator Agent detects issues, without requiring manual intervention.

**Mechanism:**
1. **Validator Agent** validates the composed itinerary
2. If issues are found (timing conflicts, budget violations, factual grounding errors), Validator signals **Planner Agent** to regenerate
3. **Planner Agent** receives specific feedback from Validator and regenerates the plan with adjustments
4. Loop repeats until:
   - Validator approves the plan, OR
   - Maximum 3 regeneration iterations reached
5. If max iterations reached without approval, system proceeds with warnings and allows human override

**Iteration Tracking:**
- State object includes `regeneration_count` counter
- Each regeneration increments the counter
- Validator checks counter before triggering next regeneration
- After 3 iterations, Validator forces approval with warnings logged

**Issue Categories Triggering Regeneration:**
- **Critical:** Impossible routing, non-existent attractions, severe budget violations
- **Major:** Tight timing (< 30 min buffer), overlapping activities, closed attractions
- **Minor:** Suboptimal scheduling, could be better timing (may not trigger regeneration)

**Regeneration Strategy:**
- Planner Agent uses Validator feedback to adjust specific problematic areas
- Budget Agent re-runs with new constraints if budget was the issue
- Workers may be re-invoked selectively (e.g., only Flight Agent if flight timing was the issue)
- Cached results from previous iterations are reused where possible

**Fallback Behavior:**
- If 3 iterations fail, system delivers plan with clear warnings and suggestions
- User sees specific issues that couldn't be resolved
- User can manually adjust constraints and retry

---

### 3.14 Agent Reasoning & Prompting

#### Reasoning: Graph of Thought (GoT)

Agents use **Graph of Thought (GoT)** reasoning—not linear chain-of-thought alone. Planning steps form a graph of hypotheses, tool results, and revisions so the Planner and workers can branch, backtrack, and merge paths when constraints conflict (e.g., budget vs. preferred hotel).

**GoT Benefits:**
- **Branching:** Explore multiple solution paths in parallel (e.g., budget hotel vs. luxury hotel)
- **Backtracking:** Abandon paths that violate constraints and try alternatives
- **Merging:** Combine successful partial solutions from different branches
- **Revision:** Update hypotheses based on new tool results or validation feedback

#### Prompting Principles

| Principle | Meaning |
|-----------|---------|
| **Constraint-first planning** | Budget, dates, and hard limits before nice-to-haves |
| **Grounded responses only** | Claims backed by tool output or verified data |
| **Tool-assisted reasoning** | Prefer MCP tool calls over speculation |
| **Preference-aware recommendations** | Apply Mem0 and episodic memory when ranking options |
| **Budget-aware optimization** | Budget Agent enforces limits before composition |
| **Validation before final output** | No user-facing plan without Validator approval |

#### Tone & Interaction Style

- Professional and friendly
- Clear and concise communication
- Ask **one** follow-up question at a time (see §4.4)
- Avoid overwhelming users with excessive detail
- Provide actionable recommendations

---

### 💬 PM Alignment: Key Design Questions for Step 3

To finalise Step 3, please provide feedback on these key agent design decisions:

1. **Agent Step Limits:** **Step limits per agent** — Planner: 5, Workers: 3, Budget: 2, Composer: 3, Validator: 2
2. **Parallel Worker Timeout:** Wait for a configurable timeout, then proceed with available results, never wait indefinitely
3. **Validator Strictness:** **Warn and allow override** for Minor Issues, **Auto-Reject Only** for Major Conflicts (Time overlap, Impossible travel, Closed attraction)
4. **Agent Memory Scope:** **Planner Agent Retrieves Memory, preferences, and Workers Receive Curated Context**




