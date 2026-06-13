# Production Deployment Plan (Render & Vercel)

This document outlines the step-by-step procedure for deploying the **Real-Time Voice AI Travel Planning Multi-Agent System** using a native Python virtual environment (`venv`) on Render (Backend) and native Next.js hosting on Vercel (Frontend), integrating managed cloud services (Supabase, Upstash Redis, and Mem0 AI).

```mermaid
graph TD
    User([User's Browser])
    
    subgraph Vercel [Frontend Hosting]
        FE[Next.js App]
    end
    
    subgraph Render [Backend Hosting]
        BE[FastAPI App running in Native Python]
    end
    
    subgraph ManagedServices [Managed Services]
        DB[(Supabase PostgreSQL)]
        Redis[(Upstash Redis)]
        Mem0[(Mem0 AI)]
        LLM[Groq & Gemini APIs]
        TTS[ElevenLabs API]
        MCP[Multi-MCP Server]
    end

    User -->|HTTPS| FE
    FE -->|API Requests / SSE| BE
    BE -->|SQL / Pooler| DB
    BE -->|Caching / Session| Redis
    BE -->|Memory Store| Mem0
    BE -->|Orchestration| LLM
    BE -->|Voice TTS| TTS
    BE -->|Search & Tools| MCP
```

---

## Prerequisites

Before starting the deployment, ensure you have active accounts on the following platforms:
1. **GitHub**: To host the repository and trigger auto-deployments.
2. **Supabase**: For the managed PostgreSQL database and User Authentication.
3. **Upstash**: For serverless Redis caching.
4. **Render**: For hosting the FastAPI native Python backend.
5. **Vercel**: For hosting the Next.js frontend.
6. **External API Providers**: Groq, Google AI Studio, Mem0 AI, and ElevenLabs.

---

## Phase 1: Database & Cache Setup (Managed Services)

### 1. Supabase (Database & Authentication)
1. Log in to [Supabase](https://supabase.com/) and click **New Project**.
2. Select your Organization, enter a project name (e.g., `Voice AI Travel Planner`), choose a Region, and set a strong database password.
3. Once the database is ready, go to **Project Settings** → **Database**:
   - Save your **Connection string** (URI mode) under port `5432` or transaction pooler `6543`.
   - Save your **Database Password** (needed for migration).
4. Go to **Project Settings** → **API**:
   - Save the **Project URL** (`SUPABASE_URL`).
   - Save the `anon` public key (`SUPABASE_ANON_KEY`).
   - Save the `service_role` private key (`SUPABASE_SERVICE_KEY`).

### 2. Upstash (Redis Cache)
1. Log in to [Upstash](https://upstash.com/) and select **Redis**.
2. Click **Create Database**. Set database name (e.g., `travel-cache`) and select the nearest region.
3. Copy the **Redis URL** (should start with `rediss://`) and the **password/token** (`UPSTASH_REDIS_TOKEN`).

---

## Phase 2: Schema Deployment & Data Migration

For database setup, you must apply the database schemas to Supabase and migrate any existing local development data.

### 1. Apply Database Migrations
Use your database client or the Supabase SQL Editor to run the SQL migrations located in:
1. [001_initial_schema.sql](file:///c:/Users/HP/OneDrive/Desktop/shiv/programming%20project/Git_hub%20project/Real-Time%20Voice%20AI%20Travel%20Planning%20Multi-Agent%20System/backend/supabase/migrations/001_initial_schema.sql): Sets up tables (`users`, `profiles`, `trips`, `itineraries`, `chat_messages`, etc.).
2. [002_add_preferences_to_profiles.sql](file:///c:/Users/HP/OneDrive/Desktop/shiv/programming%20project/Git_hub%20project/Real-Time%20Voice%20AI%20Travel%20Planning%20Multi-Agent%20System/backend/supabase/migrations/002_add_preferences_to_profiles.sql): Adds personalization columns.
3. [add_performance_indexes.sql](file:///c:/Users/HP/OneDrive/Desktop/shiv/programming%20project/Git_hub%20project/Real-Time%20Voice%20AI%20Travel%20Planning%20Multi-Agent%20System/backend/migrations/add_performance_indexes.sql): Adds read-path indexing for lower latency.

### 2. Run Data Migration Script
To transfer any existing accounts and trips from your local PostgreSQL database (run in Docker) to Supabase, run the migration script:
1. Ensure your local postgres container is running:
   ```bash
   docker-compose up -d postgres
   ```
2. Configure your root `.env` file with both local and production variables:
   ```env
   # Local database (source)
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/travel_db
   
   # Target managed credentials
   SUPABASE_URL=https://<your-project-ref>.supabase.co
   SUPABASE_SERVICE_KEY=<your-service-role-key>
   SUPABASE_DB_PASSWORD=<your-db-password>
   UPSTASH_REDIS_URL=rediss://<your-upstash-redis-url>
   UPSTASH_REDIS_TOKEN=<your-upstash-token>
   ```
3. Open your terminal in the project root, activate your virtual environment, and execute the migration script:
   * **On Windows (PowerShell):**
     ```powershell
     # Activate backend virtual environment
     .\backend\.venv\Scripts\Activate.ps1
     
     # Run the migration
     python scripts/migrate_to_managed.py
     ```
   * **On macOS/Linux:**
     ```bash
     source backend/venv/bin/activate
     python scripts/migrate_to_managed.py
     ```
   *This script verifies the connection, migrates tables, compares row counts, enables Row Level Security (RLS) on Supabase, and performs read/write checks on Upstash.*
## But Currently in Phase 2: Schema & Data (Managed Services Direct)

Since the database schema is already deployed directly on the managed services (Supabase PostgreSQL, Upstash Redis), no local schema deployment or data migration steps are required for this deployment. Ensure the managed services database and caches are active.
---

## Phase 3: Backend Deployment (Render - Native Python)

Instead of using Docker, the backend runs natively in a Python environment. **The backend requires Python 3.11.x (specifically Python 3.11.9)**. 

Render will automatically build the environment and install requirements from `requirements.txt`. You can deploy this either through the Render Dashboard interface or declaratively using the [render.yaml](file:///c:/Users/HP/OneDrive/Desktop/shiv/programming%20project/Git_hub%20project/Real-Time%20Voice%20AI%20Travel%20Planning%20Multi-Agent%20System/render.yaml) file at the root of your repository.

### 1. Create Web Service on Render (Manual Way)
1. Log in to [Render](https://render.com/) and click **New** → **Web Service**.
2. Connect your Git repository.
3. Configure the service settings:
   - **Name**: `voice-travel-backend`
   - **Environment**: `Python`
   - **Root Directory**: `backend` *(Setting this to `backend` ensures Render installs from `backend/requirements.txt` and sets `backend` as the working directory)*
   - **Build Command**: `pip install -r requirements.txt` *(Render runs this automatically inside its virtual environment)*
   - **Start Command**: `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 2. Set Environment Variables on Render
Add the following Environment Variables in the **Variables** tab:

| Variable Name | Production Value | Description |
| :--- | :--- | :--- |
| `PYTHON_VERSION` | `3.11.9` | Enforces the backend's Python runtime version |
| `APP_ENV` | `production` | Enables production mode and logging |
| `SUPABASE_URL` | `https://dqbhkfz....supabase.co` | Your Supabase project HTTP API URL |
| `SUPABASE_ANON_KEY` | `eyJhbGc.....` | Your Supabase anonymous public key |
| `SUPABASE_SERVICE_KEY` | `eyJhbG.....` | Your Supabase service role private key |  
| `SUPABASE_DB_PASSWORD` | `xyz` | Your Supabase database password (required for building the DB connection URI) |
| `DATABASE_URL` | `postgresql://postgres.[project-id]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres` | Your Supabase Connection Pooler URL (IPv4-compatible, required because Render does not support IPv6 direct connections on port 5432) |
| `UPSTASH_REDIS_URL` | `rediss://default:[token]@<your-upstash-endpoint>:6379` | Your Upstash Redis URL endpoint |
| `UPSTASH_REDIS_TOKEN` | `gQA...` | Your Upstash Redis authorization token |
| `CORS_ORIGINS` | `https://<your-frontend>.vercel.app` | URL of your deployed Vercel frontend |
| `GROQ_API_KEY` | `gsk_...` | Groq API Key (for LLM and Whisper STT) | 
| `GEMINI_API_KEY` | `AIzaSy...` | Gemini API Key (for worker agents) |
| `MEM0_API_KEY` | `m0-...` | Mem0 API Key (for personalized long-term memory) |
| `ELEVENLABS_API_KEY`| `sk_...` | ElevenLabs API Key (for text-to-speech) |
| `MCP_SERVER_URL` | `https://multi-mcp-servers.onrender.com` | MCP routing URL (Aviationstack, Maps, Tavily, etc.) |

*Save the variables. Render will automatically install packages and deploy the FastAPI server.*

---

## Phase 4: Frontend Deployment (Vercel)

Vercel provides native, optimized deployment for Next.js applications.

### 1. Configure Project on Vercel
1. Log in to [Vercel](https://vercel.com/) and click **Add New** → **Project**.
2. Import your Git repository.
3. Configure project settings:
   - **Framework Preset**: `Next.js`
   - **Root Directory**: `frontend` *(Ensure this is set to `frontend` so Vercel compiles from the right subfolder)*
   - **Build Command**: `next build`
   - **Output Directory**: `.next`

### 2. Configure Frontend Environment Variables
Add these environment variables under Vercel **Environment Variables**:

| Variable Name | Value | Description |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_URL` | `https://voice-travel-backend.onrender.com` | URL of the deployed Render backend (no trailing slash) |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<your-project-ref>.supabase.co` | Supabase URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJhbGciOiJIUzI1NiIsInR5c...` | Supabase Anon Key |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | `...apps.googleusercontent.com` | Google OAuth client ID (if using Google Auth) |

*Click **Deploy**. Vercel will build and serve your Next.js application.*

---

## Phase 5: Verification & Production Monitoring

### 1. Verify Deployment Handshake
1. Open your deployed Vercel frontend URL.
2. Open Browser DevTools (Console and Network tab) and verify:
   - The landing page mounts with high-brightness background styles.
   - The connection to the Render backend is successful.
   - Test text queries generate itineraries correctly.
   - Real-time and transcription voice modes successfully communicate with the backend's audio processing endpoints.

### 2. Monitor Services
- **Render Logs**: Check for any python compilation or startup runtime exceptions.
- **Supabase Dashboard**: Monitor active API connections, user table counts, and read latency performance.
- **Upstash Dashboard**: Monitor cache hit/miss ratio, connection counts, and latency.
- **Vercel Analytics**: Monitor frontend load speed, Web Vitals, and serverless function statuses.
