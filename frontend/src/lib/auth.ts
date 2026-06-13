/**
 * Auth helpers — Supabase client + session utilities.
 * Used by protected pages and the NavBar.
 */
import { createClient, type SupabaseClient, type User } from "@supabase/supabase-js";

// ── Supabase client (browser singleton) ─────────────────────────────────

const supabaseUrl  = process.env.NEXT_PUBLIC_SUPABASE_URL  ?? "";
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

let _client: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
  if (!_client) {
    _client = createClient(supabaseUrl, supabaseAnon, {
      auth: {
        persistSession:    true,
        autoRefreshToken:  true,
        detectSessionInUrl: true,
      },
    });
  }
  return _client;
}

// ── Session helpers ──────────────────────────────────────────────────────

/**
 * Returns the current Supabase session access_token or null if not signed in.
 */
export async function getAccessToken(): Promise<string | null> {
  try {
    const { data } = await getSupabaseClient().auth.getSession();
    return data.session?.access_token ?? null;
  } catch (err) {
    console.warn("Error calling getAccessToken:", err);
    return null;
  }
}

/**
 * Returns the current Supabase user or null.
 */
export async function getCurrentUser(): Promise<User | null> {
  const { data } = await getSupabaseClient().auth.getUser();
  return data.user ?? null;
}

/**
 * Returns true when the user has an active session.
 */
export async function isAuthenticated(): Promise<boolean> {
  const token = await getAccessToken();
  return token !== null;
}

/**
 * Sign out the current user and redirect to login.
 */
export async function signOut(): Promise<void> {
  await getSupabaseClient().auth.signOut();
  window.location.href = "/login";
}

/**
 * Sign in with email + password.
 */
export async function signInWithPassword(email: string, password: string) {
  return getSupabaseClient().auth.signInWithPassword({ email, password });
}

/**
 * Sign up with email + password.
 */
export async function signUpWithPassword(email: string, password: string) {
  return getSupabaseClient().auth.signUp({ email, password });
}

/**
 * Sign in with Google OAuth.
 */
export async function signInWithGoogle() {
  return getSupabaseClient().auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: `${window.location.origin}/` },
  });
}
