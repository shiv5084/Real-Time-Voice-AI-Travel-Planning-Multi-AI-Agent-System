-- Database Performance Optimization: Add Indexes for Frequently Queried Columns
-- This migration adds indexes to optimize query performance for the travel planning system

-- Index on profiles table for user lookups
CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_display_name ON profiles(display_name);

-- Index on trips table for user trip listings (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_trips_user_id ON trips(user_id);
CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);
CREATE INDEX IF NOT EXISTS idx_trips_created_at ON trips(created_at DESC);
-- Composite index for user's trips ordered by date
CREATE INDEX IF NOT EXISTS idx_trips_user_created ON trips(user_id, created_at DESC);

-- Index on itineraries table for trip lookups
CREATE INDEX IF NOT EXISTS idx_itineraries_trip_id ON itineraries(trip_id);
CREATE INDEX IF NOT EXISTS idx_itineraries_validation_status ON itineraries(validation_status);

-- Index on audit_log table for trace-based queries and analytics
CREATE INDEX IF NOT EXISTS idx_audit_log_trace_id ON audit_log(trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_trip_id ON audit_log(trip_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_agent ON audit_log(agent);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);
-- Composite index for agent performance analytics
CREATE INDEX IF NOT EXISTS idx_audit_log_agent_created ON audit_log(agent, created_at DESC);

-- Index on preferences table for user preference lookups (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'preferences') THEN
        CREATE INDEX IF NOT EXISTS idx_preferences_user_id ON preferences(user_id);
        CREATE INDEX IF NOT EXISTS idx_preferences_key ON preferences(key);
    END IF;
END $$;

-- Index on episodic_memory table for user memory retrieval (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'episodic_memory') THEN
        CREATE INDEX IF NOT EXISTS idx_episodic_memory_user_id ON episodic_memory(user_id);
        CREATE INDEX IF NOT EXISTS idx_episodic_memory_destination ON episodic_memory(destination);
        CREATE INDEX IF NOT EXISTS idx_episodic_memory_created_at ON episodic_memory(created_at DESC);
    END IF;
END $$;

-- Partial index for active trips only (optimizes common queries)
CREATE INDEX IF NOT EXISTS idx_trips_active ON trips(user_id, created_at DESC)
WHERE status IN ('planning', 'approved', 'in_progress');

-- Comment on migration
COMMENT ON INDEX idx_trips_user_id IS 'Optimizes user trip listing queries';
COMMENT ON INDEX idx_trips_user_created IS 'Optimizes user trip history with date ordering';
COMMENT ON INDEX idx_audit_log_trace_id IS 'Optimizes trace-based debugging queries';
COMMENT ON INDEX idx_trips_active IS 'Optimizes active trip queries with partial index';
