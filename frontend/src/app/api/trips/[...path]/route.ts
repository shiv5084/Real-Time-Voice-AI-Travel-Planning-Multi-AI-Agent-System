/**
 * Catch-all Route Handler for /api/trips/[...path]
 *
 * Handles:  GET/DELETE /api/trips, GET /api/trips/{id}/status, POST /api/trips/followup
 *
 * These endpoints are fast (< 5 s), so a 60-second timeout is fine.
 * We still proxy them here so ALL /api/trips/* traffic goes through Route
 * Handlers and never through the rewrite proxy, keeping the proxy
 * conflict-free.
 *
 * NOTE: /api/trips/plan has its own route.ts with a longer timeout.
 */

import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function proxy(req: NextRequest, segments: string[]): Promise<NextResponse> {
  const path = segments.join("/");
  const backendUrl = `${BACKEND}/api/trips/${path}${req.nextUrl.search ?? ""}`;

  const forwardHeaders: Record<string, string> = {};
  const ct = req.headers.get("Content-Type");
  if (ct) forwardHeaders["Content-Type"] = ct;
  const auth = req.headers.get("Authorization");
  if (auth) forwardHeaders["Authorization"] = auth;

  const hasBody = req.method !== "GET" && req.method !== "DELETE" && req.method !== "HEAD";
  const body = hasBody ? await req.text() : undefined;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60_000); // 60 s for fast endpoints

  try {
    const resp = await fetch(backendUrl, {
      method: req.method,
      headers: forwardHeaders,
      body,
      signal: controller.signal,
    });

    // 204 No Content
    if (resp.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    const text = await resp.text();
    return new NextResponse(text, {
      status: resp.status,
      headers: {
        "Content-Type": resp.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      return NextResponse.json({ detail: "Request timed out" }, { status: 504 });
    }
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ detail: `Proxy error: ${msg}` }, { status: 502 });
  } finally {
    clearTimeout(timer);
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path ?? []);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path ?? []);
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path ?? []);
}
