"use client";

/**
 * Phase 1 Exit Criteria — Manual Test Page
 * "Google OAuth flow returns valid JWT"
 *
 * What this page does:
 *  1. Renders a Google Sign-In button using the Google Identity Services SDK
 *  2. On sign-in, sends the Google id_token to POST /auth/google on your FastAPI backend
 *  3. Displays the raw response (access_token, user object)
 *  4. Decodes the access_token JWT payload inline so you can verify sub, email, exp
 *  5. Calls GET /auth/me with that token to confirm the protected route works
 *
 * Prerequisites:
 *  - Add NEXT_PUBLIC_GOOGLE_CLIENT_ID to frontend/.env.local
 *  - All four Docker services must be running (postgres, redis, backend, frontend)
 *  - Supabase project must have Google provider enabled with your OAuth credentials
 */

import { useEffect, useRef, useState } from "react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface AuthResponse {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    display_name: string | null;
    avatar_url: string | null;
  };
}

interface JwtPayload {
  sub: string;
  email: string;
  exp: number;
  iat: number;
  [key: string]: unknown;
}

interface TestResult {
  step: string;
  status: "pass" | "fail" | "pending";
  detail: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64);
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

function formatExpiry(exp: number): string {
  const date = new Date(exp * 1000);
  const now = new Date();
  const isFuture = date > now;
  return `${date.toLocaleString()} — ${isFuture ? "✅ valid (future)" : "❌ expired"}`;
}

// ─── Google GSI SDK types (minimal) ─────────────────────────────────────────

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
            ux_mode?: string;
          }) => void;
          renderButton: (
            element: HTMLElement,
            config: {
              theme?: string;
              size?: string;
              text?: string;
              shape?: string;
              width?: number;
            }
          ) => void;
          prompt: () => void;
        };
      };
    };
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function AuthTestPage() {
  const API_URL =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const GOOGLE_CLIENT_ID =
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

  const googleBtnRef = useRef<HTMLDivElement>(null);
  const [sdkReady, setSdkReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [authResponse, setAuthResponse] = useState<AuthResponse | null>(null);
  const [meResponse, setMeResponse] = useState<AuthResponse["user"] | null>(null);
  const [jwtPayload, setJwtPayload] = useState<JwtPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<TestResult[]>([]);

  // ── Load Google GSI SDK ───────────────────────────────────────────────────
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;

    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => setSdkReady(true);
    document.head.appendChild(script);

    return () => {
      document.head.removeChild(script);
    };
  }, [GOOGLE_CLIENT_ID]);

  // ── Render Google button once SDK is ready ────────────────────────────────
  useEffect(() => {
    if (!sdkReady || !window.google || !googleBtnRef.current || !GOOGLE_CLIENT_ID)
      return;

    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: handleGoogleCredential,
      ux_mode: "popup",
    });

    window.google.accounts.id.renderButton(googleBtnRef.current, {
      theme: "filled_blue",
      size: "large",
      text: "signin_with",
      shape: "rectangular",
      width: 280,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sdkReady, GOOGLE_CLIENT_ID]);

  // ── OAuth callback → call backend ─────────────────────────────────────────
  async function handleGoogleCredential(response: { credential: string }) {
    setLoading(true);
    setError(null);
    setAuthResponse(null);
    setMeResponse(null);
    setJwtPayload(null);
    setResults([]);

    const idToken = response.credential;
    const stepResults: TestResult[] = [];

    // Step 1: POST /auth/google
    let accessToken = "";
    try {
      const res = await fetch(`${API_URL}/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: idToken }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }

      const data: AuthResponse = await res.json();
      setAuthResponse(data);
      accessToken = data.access_token;

      stepResults.push({
        step: "POST /auth/google → 200 OK",
        status: "pass",
        detail: `Received access_token (${accessToken.length} chars) for ${data.user.email}`,
      });
    } catch (err) {
      stepResults.push({
        step: "POST /auth/google",
        status: "fail",
        detail: String(err),
      });
      setResults(stepResults);
      setError(String(err));
      setLoading(false);
      return;
    }

    // Step 2: Decode JWT payload
    const payload = decodeJwtPayload(accessToken);
    setJwtPayload(payload);
    if (payload) {
      const isFuture = new Date(payload.exp * 1000) > new Date();
      stepResults.push({
        step: "JWT payload decoded",
        status: isFuture ? "pass" : "fail",
        detail: `sub=${payload.sub} | email=${payload.email} | exp=${isFuture ? "future ✅" : "expired ❌"}`,
      });
    } else {
      stepResults.push({
        step: "JWT payload decoded",
        status: "fail",
        detail: "Could not decode token — not a valid JWT?",
      });
    }

    // Step 3: GET /auth/me
    try {
      const meRes = await fetch(`${API_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (!meRes.ok) {
        throw new Error(`HTTP ${meRes.status}`);
      }

      const meData: AuthResponse["user"] = await meRes.json();
      setMeResponse(meData);
      stepResults.push({
        step: "GET /auth/me with JWT → 200 OK",
        status: "pass",
        detail: `Protected route returned user id=${meData.id}`,
      });
    } catch (err) {
      stepResults.push({
        step: "GET /auth/me with JWT",
        status: "fail",
        detail: String(err),
      });
    }

    setResults(stepResults);
    setLoading(false);
  }

  // ─── Render ────────────────────────────────────────────────────────────────

  const allPass =
    results.length > 0 && results.every((r) => r.status === "pass");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 px-4 py-10">
      <div className="mx-auto max-w-3xl space-y-8">

        {/* Header */}
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-emerald-400 mb-1">
            Phase 1 — Manual Exit Criteria Test
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">
            Google OAuth → JWT Verification
          </h1>
          <p className="mt-2 text-slate-400 text-sm">
            Signs in with Google, sends the{" "}
            <code className="text-emerald-300">id_token</code> to{" "}
            <code className="text-emerald-300">POST /auth/google</code>, decodes
            the returned JWT, and verifies the protected{" "}
            <code className="text-emerald-300">GET /auth/me</code> endpoint.
          </p>
        </div>

        {/* Config check */}
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4 text-sm space-y-1">
          <p className="font-medium text-slate-300 mb-2">Environment</p>
          <ConfigRow
            label="NEXT_PUBLIC_API_URL"
            value={API_URL}
            ok={!!API_URL}
          />
          <ConfigRow
            label="NEXT_PUBLIC_GOOGLE_CLIENT_ID"
            value={
              GOOGLE_CLIENT_ID
                ? `${GOOGLE_CLIENT_ID.slice(0, 12)}…`
                : "NOT SET"
            }
            ok={!!GOOGLE_CLIENT_ID}
          />
          <ConfigRow
            label="Google GSI SDK"
            value={sdkReady ? "loaded" : "loading…"}
            ok={sdkReady}
          />
        </div>

        {/* Warning if client ID missing */}
        {!GOOGLE_CLIENT_ID && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-300">
            <strong>Missing NEXT_PUBLIC_GOOGLE_CLIENT_ID.</strong> Add it to{" "}
            <code>frontend/.env.local</code> and restart the frontend container.
            <pre className="mt-2 text-xs text-amber-400">
              NEXT_PUBLIC_GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
            </pre>
          </div>
        )}

        {/* Sign-in button */}
        {GOOGLE_CLIENT_ID && (
          <div className="flex flex-col items-start gap-3">
            <p className="text-sm text-slate-400">
              Click the button below to start the test:
            </p>
            <div ref={googleBtnRef} />
            {!sdkReady && (
              <p className="text-xs text-slate-500">Loading Google SDK…</p>
            )}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="text-sm text-slate-400 animate-pulse">
            Running test steps…
          </div>
        )}

        {/* Test results checklist */}
        {results.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-slate-300">Test Results</p>
            {results.map((r, i) => (
              <div
                key={i}
                className={`rounded-lg border p-3 text-sm ${
                  r.status === "pass"
                    ? "border-emerald-500/40 bg-emerald-500/10"
                    : "border-red-500/40 bg-red-500/10"
                }`}
              >
                <span
                  className={
                    r.status === "pass" ? "text-emerald-400" : "text-red-400"
                  }
                >
                  {r.status === "pass" ? "✅" : "❌"} {r.step}
                </span>
                <p className="mt-0.5 text-slate-400 text-xs">{r.detail}</p>
              </div>
            ))}

            {allPass && (
              <div className="rounded-lg border border-emerald-400/50 bg-emerald-400/10 p-4 text-center font-semibold text-emerald-300">
                🎉 All checks passed — Phase 1 Google OAuth exit criterion met
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Raw auth response */}
        {authResponse && (
          <Section title="Backend Response — POST /auth/google">
            <JsonBlock data={authResponse} />
          </Section>
        )}

        {/* Decoded JWT */}
        {jwtPayload && (
          <Section title="Decoded JWT Payload (access_token)">
            <div className="space-y-1 text-sm">
              <Row label="sub" value={jwtPayload.sub} />
              <Row label="email" value={String(jwtPayload.email ?? "—")} />
              <Row label="exp" value={formatExpiry(jwtPayload.exp)} />
              <Row
                label="iat"
                value={new Date(jwtPayload.iat * 1000).toLocaleString()}
              />
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-400">
                Full payload
              </summary>
              <JsonBlock data={jwtPayload} />
            </details>
          </Section>
        )}

        {/* /auth/me response */}
        {meResponse && (
          <Section title="Protected Route — GET /auth/me">
            <JsonBlock data={meResponse} />
          </Section>
        )}

        {/* Back link */}
        <div className="pt-4 border-t border-slate-800">
          <a
            href="/"
            className="text-sm text-slate-500 hover:text-slate-300 transition"
          >
            ← Back to home
          </a>
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ConfigRow({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className={ok ? "text-emerald-400" : "text-amber-400"}>
        {ok ? "✅" : "⚠️"}
      </span>
      <span className="text-slate-400 w-64">{label}</span>
      <span className="text-slate-300 font-mono text-xs">{value}</span>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-3">
        {title}
      </p>
      {children}
    </div>
  );
}

function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="overflow-auto rounded bg-slate-800 p-3 text-xs text-slate-300 max-h-64">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <span className="text-slate-500 w-16 shrink-0">{label}</span>
      <span className="text-slate-200 font-mono text-xs break-all">{value}</span>
    </div>
  );
}
