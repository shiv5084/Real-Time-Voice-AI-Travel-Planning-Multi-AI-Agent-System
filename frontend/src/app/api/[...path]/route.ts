/**
 * Catch-all Route Handler for /api/[...path]
 *
 * Covers everything not matched by more specific routes:
 *   /api/auth/*, /api/health, /api/itineraries/*, /api/profile/*
 *
 * These are all fast endpoints (< 10 s). 30-second timeout is safe.
 */

import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function proxyGeneric(req: NextRequest, segments: string[]): Promise<NextResponse> {
  const path = segments.join("/");
  const prefix = (segments[0] === "auth" || segments[0] === "health") ? "" : "api/";
  const backendUrl = `${BACKEND}/${prefix}${path}${req.nextUrl.search ?? ""}`;

  const forwardHeaders: Record<string, string> = {};
  const ct = req.headers.get("Content-Type");
  if (ct) forwardHeaders["Content-Type"] = ct;
  const auth = req.headers.get("Authorization");
  if (auth) forwardHeaders["Authorization"] = auth;

  const hasBody = req.method !== "GET" && req.method !== "DELETE" && req.method !== "HEAD";
  const body = hasBody ? await req.arrayBuffer() : undefined;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);

  try {
    const resp = await fetch(backendUrl, {
      method: req.method,
      headers: forwardHeaders,
      body,
      signal: controller.signal,
    });

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

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxyGeneric(req, path ?? []);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxyGeneric(req, path ?? []);
}
export async function PUT(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxyGeneric(req, path ?? []);
}
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxyGeneric(req, path ?? []);
}
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxyGeneric(req, path ?? []);
}
