/**
 * Route Handler for POST /api/trips/plan
 *
 * WHY this exists:
 * The Next.js rewrite proxy (next.config.ts rewrites()) has a hard socket
 * timeout of ~60 seconds. The LangGraph pipeline can take 60-120 s, so the
 * proxy drops the socket mid-request → ECONNRESET.
 *
 * Route Handlers bypass the proxy and run inside the Next.js Node.js server
 * directly, so they can wait as long as the underlying fetch allows.
 * We give the backend 5 minutes before aborting.
 */

import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// Tell Vercel / Next.js edge runtime the max allowed duration (seconds).
// In local dev this is ignored but doesn't hurt.
export const maxDuration = 300;

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST(req: NextRequest): Promise<NextResponse> {
  // Forward the raw body as-is
  const body = await req.text();

  // Forward relevant headers from the original browser request
  const forwardHeaders: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const auth = req.headers.get("Authorization");
  if (auth) forwardHeaders["Authorization"] = auth;

  const traceId = req.headers.get("X-Trace-Id");
  if (traceId) forwardHeaders["X-Trace-Id"] = traceId;

  // 5-minute abort controller so the browser gets a clean error instead of
  // a silent connection reset if the backend truly hangs.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5 * 60 * 1000);

  try {
    const backendResp = await fetch(`${BACKEND}/api/trips/plan`, {
      method: "POST",
      headers: forwardHeaders,
      body,
      signal: controller.signal,
      // Node.js fetch — no keep-alive tuning needed; this stays on localhost
    });

    // Stream the backend response body back to the browser as-is
    const respBody = await backendResp.text();

    return new NextResponse(respBody, {
      status: backendResp.status,
      headers: {
        "Content-Type":
          backendResp.headers.get("Content-Type") ?? "application/json",
        "X-Trace-Id": backendResp.headers.get("X-Trace-Id") ?? "",
      },
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      return NextResponse.json(
        {
          detail:
            "The trip planning pipeline timed out after 5 minutes. Please try a simpler request or try again.",
        },
        { status: 504 }
      );
    }

    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { detail: `Proxy error: ${msg}` },
      { status: 502 }
    );
  } finally {
    clearTimeout(timer);
  }
}
