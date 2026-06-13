-- Add preferences column to profiles table for persistent storage
-- This ensures user preferences persist across page refreshes

ALTER TABLE profiles ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}'::jsonb;

-- Add index for faster preference lookups
CREATE INDEX IF NOT EXISTS idx_profiles_preferences ON profiles USING GIN (preferences);
