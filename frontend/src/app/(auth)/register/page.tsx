"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { signInWithGoogle, getSupabaseClient } from "@/lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm]   = useState("");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [success, setSuccess]   = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    try {
      // Derive a friendly display name from the email (e.g. "john.doe@…" → "John Doe")
      const emailLocal = email.split("@")[0] ?? email;
      const displayName = emailLocal
        .replace(/[._-]+/g, " ")
        .split(" ")
        .filter(Boolean)
        .map((w: string) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");

      // Step 1: Create the Supabase auth user, embedding display_name in metadata
      const supabase = getSupabaseClient();
      const { data, error: authError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${window.location.origin}/`,
          data: {
            display_name: displayName,
            full_name: displayName,
          },
        },
      });
      if (authError) throw authError;

      const user = data.user;
      if (!user) throw new Error("Registration succeeded but no user returned");

      // Step 2: Create the profile row via the backend (service-role key bypasses RLS)
      const profileRes = await fetch(`/api/auth/create-profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, user_id: user.id, display_name: displayName }),
      });

      // 409 = profile already exists — that's fine
      if (!profileRes.ok && profileRes.status !== 409) {
        console.warn("Profile creation failed (non-fatal):", profileRes.status);
      }

      setSuccess(true);
      setTimeout(() => router.push("/register/onboarding"), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    setLoading(true);
    try {
      const { error: authError } = await signInWithGoogle();
      if (authError) throw authError;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Google sign-in failed");
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center px-4">
        <div className="card max-w-md text-center animate-slide-up">
          <div className="mb-4 text-5xl">✅</div>
          <h2 className="mb-2 text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Account created!
          </h2>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Redirecting to set up your preferences…
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center px-4">
      <div className="card w-full max-w-md animate-slide-up">
        <h1
          className="mb-2 text-center text-2xl font-bold"
          style={{ color: "var(--text-primary)" }}
        >
          Create your account
        </h1>
        <p className="mb-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          Start planning AI-powered trips for free
        </p>

        {/* Google */}
        <button
          type="button"
          onClick={handleGoogle}
          disabled={loading}
          className="btn btn-ghost mb-4 w-full gap-2"
          aria-label="Sign up with Google"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </button>

        <div className="flex items-center gap-3 mb-4">
          <span className="flex-1 h-px" style={{ background: "var(--border)" }} />
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>or email</span>
          <span className="flex-1 h-px" style={{ background: "var(--border)" }} />
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
          <div>
            <label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="email"
              value={email} onChange={(e) => setEmail(e.target.value)}
              required className="input" placeholder="you@example.com" aria-required="true" />
          </div>

          <div>
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="new-password"
              value={password} onChange={(e) => setPassword(e.target.value)}
              required className="input" placeholder="Min 8 characters" aria-required="true" />
          </div>

          <div>
            <label htmlFor="confirm">Confirm password</label>
            <input id="confirm" type="password" autoComplete="new-password"
              value={confirm} onChange={(e) => setConfirm(e.target.value)}
              required className={`input ${confirm && confirm !== password ? "error" : ""}`}
              placeholder="Repeat password" aria-required="true" />
          </div>

          {error && (
            <p className="rounded-md px-3 py-2 text-sm" role="alert"
               style={{ background: "rgba(239,68,68,0.1)", color: "var(--error)", border: "1px solid rgba(239,68,68,0.3)" }}>
              {error}
            </p>
          )}

          <button type="submit" disabled={loading || !email || !password || !confirm}
            className="btn btn-primary mt-1 w-full">
            {loading ? "Creating account…" : "Create Account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          Already have an account?{" "}
          <Link href="/login" style={{ color: "var(--accent)" }}>Sign in</Link>
        </p>
      </div>
    </div>
  );
}
