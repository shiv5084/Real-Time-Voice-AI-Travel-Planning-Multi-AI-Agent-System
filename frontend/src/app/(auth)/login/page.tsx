"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { signInWithPassword, signInWithGoogle } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { error: authError } = await signInWithPassword(email, password);
      if (authError) throw authError;
      router.push("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
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

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center px-4">
      <div className="card w-full max-w-md animate-slide-up">
        <h1
          className="mb-2 text-center text-2xl font-bold"
          style={{ color: "var(--text-primary)" }}
        >
          Welcome back
        </h1>
        <p className="mb-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          Sign in to your VoiceTravel AI account
        </p>

        {/* Google OAuth */}
        <button
          type="button"
          onClick={handleGoogle}
          disabled={loading}
          className="btn btn-ghost mb-4 w-full gap-2"
          aria-label="Sign in with Google"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </button>

        <div className="divider flex items-center gap-3">
          <span className="flex-1 h-px" style={{ background: "var(--border)" }} />
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>or email</span>
          <span className="flex-1 h-px" style={{ background: "var(--border)" }} />
        </div>

        {/* Email / password */}
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4" noValidate>
          <div>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="input"
              placeholder="you@example.com"
              aria-required="true"
            />
          </div>

          <div>
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="input"
              placeholder="••••••••"
              aria-required="true"
            />
          </div>

          {error && (
            <p className="rounded-md px-3 py-2 text-sm" role="alert"
               style={{ background: "rgba(239,68,68,0.1)", color: "var(--error)", border: "1px solid rgba(239,68,68,0.3)" }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !email || !password}
            className="btn btn-primary mt-1 w-full"
          >
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          Don&apos;t have an account?{" "}
          <Link href="/register" style={{ color: "var(--accent)" }}>
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
