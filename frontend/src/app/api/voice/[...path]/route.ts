/**
 * Catch-all Route Handler for /api/voice/[...path]
 *
 * Covers:
 *   POST /api/voice/transcribe
 *   POST /api/voice/confirm
 *   POST /api/voice/synthesise
 *   POST /api/voice/session/start
 *   POST /api/voice/session/reply
 *   POST /api/voice/transcribe/stream  (SSE)
 *
 * NOTE: /api/voice/session/{id}/plan has its own route.ts for SSE streaming.
 *
 * For multipart/form-data (audio upload) we forward the raw body so the
 * backend's FastAPI File() / Form() parsing still works.
 */

import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 120; // 2 min — enough for STT + TTS

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function proxyVoice(req: NextRequest, segments: string[]): Promise<NextResponse | Response> {
  const path = segments.join("/");
  const backendUrl = `${BACKEND}/api/voice/${path}`;

  // Build forwarded headers — preserve Content-Type exactly so multipart
  // form-data boundaries pass through intact to FastAPI.
  const forwardHeaders: Record<string, string> = {};
  const ct = req.headers.get("Content-Type");
  if (ct) forwardHeaders["Content-Type"] = ct;
  const auth = req.headers.get("Authorization");
  if (auth) forwardHeaders["Authorization"] = auth;

  // Check if this is an SSE endpoint (transcribe/stream)
  const isSSE = path.endsWith("/stream");
  if (isSSE) {
    forwardHeaders["Accept"] = "text/event-stream";
    forwardHeaders["Cache-Control"] = "no-cache";
  }

  // Read body as ArrayBuffer to preserve binary data (audio uploads)
  const bodyBytes = req.method !== "GET" ? await req.arrayBuffer() : undefined;

  const controller = new AbortController();
  const timeoutMs = isSSE ? 120_000 : 60_000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const resp = await fetch(backendUrl, {
      method: req.method,
      headers: forwardHeaders,
      body: bodyBytes,
      signal: controller.signal,
    });

    // For SSE endpoints, stream the body back
    if (isSSE && resp.ok && resp.body) {
      clearTimeout(timer);
      return new Response(resp.body, {
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
          "X-Accel-Buffering": "no",
        },
      });
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
      return NextResponse.json({ detail: "Voice request timed out" }, { status: 504 });
    }
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ detail: `Voice proxy error: ${msg}` }, { status: 502 });
  } finally {
    clearTimeout(timer);
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyVoice(req, path ?? []);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyVoice(req, path ?? []);
}
