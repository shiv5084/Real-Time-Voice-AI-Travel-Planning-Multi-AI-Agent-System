/**
 * Route Handler for GET /api/voice/session/[session_id]/plan
 *
 * This endpoint streams SSE events for the duration of the LangGraph pipeline
 * (60-120 s). The Next.js rewrite proxy would kill the stream early.
 *
 * We proxy the SSE stream directly from the backend to the browser,
 * forwarding bytes as they arrive.
 */

import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ session_id: string }> }
) {
  const { session_id } = await params;

  const forwardHeaders: Record<string, string> = {
    Accept: "text/event-stream",
    "Cache-Control": "no-cache",
  };
  const auth = req.headers.get("Authorization");
  if (auth) forwardHeaders["Authorization"] = auth;

  // No AbortController here — let the SSE stream run until the backend closes it
  const backendResp = await fetch(
    `${BACKEND}/api/voice/session/${session_id}/plan`,
    {
      method: "GET",
      headers: forwardHeaders,
      cache: "no-store",
    }
  );

  if (!backendResp.ok || !backendResp.body) {
    const text = await backendResp.text().catch(() => "Unknown error");
    return new Response(text, { status: backendResp.status });
  }

  // Stream the backend SSE body straight to the browser
  return new Response(backendResp.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
