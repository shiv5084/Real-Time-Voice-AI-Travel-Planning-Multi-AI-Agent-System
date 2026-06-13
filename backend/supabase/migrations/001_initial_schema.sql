-- =============================================
-- Phase 1: Initial Database Schema
-- Real-Time Voice AI Travel Planning Multi-Agent System
-- =============================================
-- This schema creates 6 core tables for the travel planning system.
-- RLS policies are defined but enforcement is deferred to Phase 7 migration.
-- For local development (Phases 0-6), app-level user_id filtering is used.
-- =============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================
-- Users & Auth (managed by Supabase Auth)
-- =============================================

-- For local development, create a simple users table
-- In production, this is managed by Supabase Auth
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User Profiles
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT,
    email TEXT UNIQUE NOT NULL,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trip Plans
CREATE TABLE IF NOT EXISTS trips (
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
CREATE TABLE IF NOT EXISTS itineraries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID REFERENCES trips(id) ON DELETE CASCADE,
    content JSONB NOT NULL,     -- Day-by-day structured itinerary
    budget_breakdown JSONB,
    validation_status TEXT,     -- approved | warnings | rejected
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Episodic Memory (past trip learnings)
CREATE TABLE IF NOT EXISTS episodic_memory (
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
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID REFERENCES trips(id) ON DELETE CASCADE,
    role TEXT NOT NULL,          -- user | assistant | system
    content TEXT NOT NULL,
    metadata JSONB,             -- {agent, tool, trace_id}
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Log (agent observability)
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id TEXT NOT NULL,
    trip_id UUID REFERENCES trips(id),
    agent TEXT NOT NULL,
    model TEXT,
    tool TEXT,
    client TEXT,                -- Phase 2: MCP client name (aviationstack, tavily, etc.)
    arguments JSONB,
    result JSONB,
    latency_ms INTEGER,
    cost_usd NUMERIC(10, 6),
    cache_hit BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- Indexes for performance
-- =============================================

CREATE INDEX IF NOT EXISTS idx_trips_user_id ON trips(user_id);
CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);
CREATE INDEX IF NOT EXISTS idx_itineraries_trip_id ON itineraries(trip_id);
CREATE INDEX IF NOT EXISTS idx_episodic_memory_user_id ON episodic_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_episodic_memory_destination ON episodic_memory(destination);
CREATE INDEX IF NOT EXISTS idx_chat_messages_trip_id ON chat_messages(trip_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_trace_id ON audit_log(trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_trip_id ON audit_log(trip_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);

-- =============================================
-- Row Level Security (RLS) Policies
-- NOTE: These policies are defined but NOT enforced until Phase 7 migration.
-- For local development (Phases 0-6), app-level user_id filtering is used.
-- =============================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE trips ENABLE ROW LEVEL SECURITY;
ALTER TABLE itineraries ENABLE ROW LEVEL SECURITY;
ALTER TABLE episodic_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Profiles: Users can read/write their own profile
CREATE POLICY "Users can view own profile" ON profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON profiles
    FOR UPDATE USING (auth.uid() = id);

-- Trips: Users can read/write their own trips
CREATE POLICY "Users can view own trips" ON trips
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Users can create own trips" ON trips
    FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update own trips" ON trips
    FOR UPDATE USING (user_id = auth.uid());

CREATE POLICY "Users can delete own trips" ON trips
    FOR DELETE USING (user_id = auth.uid());

-- Itineraries: Users can read itineraries for their own trips
CREATE POLICY "Users can view own itineraries" ON itineraries
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM trips WHERE trips.id = itineraries.trip_id AND trips.user_id = auth.uid())
    );

-- Episodic Memory: Users can read/write their own memories
CREATE POLICY "Users can view own memories" ON episodic_memory
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Users can create own memories" ON episodic_memory
    FOR INSERT WITH CHECK (user_id = auth.uid());

-- Chat Messages: Users can read messages for their own trips
CREATE POLICY "Users can view own chat messages" ON chat_messages
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM trips WHERE trips.id = chat_messages.trip_id AND trips.user_id = auth.uid())
    );

CREATE POLICY "Users can create own chat messages" ON chat_messages
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM trips WHERE trips.id = chat_messages.trip_id AND trips.user_id = auth.uid())
    );

-- Audit Log: Users can view audit logs for their own trips (read-only observability)
CREATE POLICY "Users can view own audit logs" ON audit_log
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM trips WHERE trips.id = audit_log.trip_id AND trips.user_id = auth.uid())
    );

-- =============================================
-- Triggers for updated_at timestamps
-- =============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_trips_updated_at BEFORE UPDATE ON trips
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
