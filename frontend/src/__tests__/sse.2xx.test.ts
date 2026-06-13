/**
 * Preservation Test 2.3 — SSE 2xx streams events normally.
 *
 * Validates: Requirements 3.4
 *
 * This test MUST PASS on unfixed code. It establishes the baseline that
 * openSSE correctly streams and parses SSE events for a successful 2xx response,
 * and never calls onError.
 */

import { describe, it, expect, vi, afterEach } from "vitest";

// ── Helpers ────────────────────────────────────────────────────────────────

/** Build a ReadableStream that yields the given string chunks and then closes. */
function makeStream(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index++]));
      } else {
        controller.close();
      }
    },
  });
}

/** Mock fetch that returns a 200 with the given ReadableStream as the body. */
function mockFetch200(body: ReadableStream<Uint8Array>) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    body,
  } as unknown as Response);
}

// ── Mock auth ─────────────────────────────────────────────────────────────

vi.mock("@/lib/auth", () => ({
  getAccessToken: vi.fn().mockResolvedValue(null),
}));

// ── Import under test ──────────────────────────────────────────────────────

import { openSSE } from "@/lib/sse";

// ── Tests ──────────────────────────────────────────────────────────────────

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Preservation 2.3 — SSE 2xx streams events normally", () => {
  it("calls onMessage with parsed event object for a 2xx response", async () => {
    const sseChunk =
      "event: agent_start\ndata: {\"agent\": \"planner\", \"message\": \"Planning...\"}\n\n";

    vi.stubGlobal("fetch", mockFetch200(makeStream(sseChunk)));

    const onMessage = vi.fn();
    const onError = vi.fn();
    const onOpen = vi.fn();

    const stop = openSSE("/api/trips/plan", { onMessage, onError, onOpen });

    // Wait for the async stream to finish
    await new Promise<void>((resolve) => setTimeout(resolve, 50));
    stop();

    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith({
      event: "agent_start",
      data: { agent: "planner", message: "Planning..." },
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it("calls onOpen when the connection is established", async () => {
    const sseChunk = "event: ping\ndata: {}\n\n";

    vi.stubGlobal("fetch", mockFetch200(makeStream(sseChunk)));

    const onMessage = vi.fn();
    const onError = vi.fn();
    const onOpen = vi.fn();

    const stop = openSSE("/api/trips/plan", { onMessage, onError, onOpen });

    await new Promise<void>((resolve) => setTimeout(resolve, 50));
    stop();

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it("parses multiple events sent in a single chunk", async () => {
    const sseChunk =
      "event: agent_start\ndata: {\"agent\": \"planner\"}\n\n" +
      "event: agent_done\ndata: {\"agent\": \"planner\"}\n\n";

    vi.stubGlobal("fetch", mockFetch200(makeStream(sseChunk)));

    const onMessage = vi.fn();
    const onError = vi.fn();

    const stop = openSSE("/api/trips/plan", { onMessage, onError });

    await new Promise<void>((resolve) => setTimeout(resolve, 50));
    stop();

    expect(onMessage).toHaveBeenCalledTimes(2);
    expect(onMessage).toHaveBeenNthCalledWith(1, {
      event: "agent_start",
      data: { agent: "planner" },
    });
    expect(onMessage).toHaveBeenNthCalledWith(2, {
      event: "agent_done",
      data: { agent: "planner" },
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it("parses events split across multiple stream chunks (split at event boundary)", async () => {
    // Split between two complete SSE events — each chunk contains one full event
    const chunk1 = "event: plan_complete\ndata: {\"status\": \"done\"}\n\n";
    const chunk2 = "event: voice_summary\ndata: {\"text\": \"Paris\"}\n\n";

    vi.stubGlobal("fetch", mockFetch200(makeStream(chunk1, chunk2)));

    const onMessage = vi.fn();
    const onError = vi.fn();

    const stop = openSSE("/api/trips/plan", { onMessage, onError });

    await new Promise<void>((resolve) => setTimeout(resolve, 50));
    stop();

    expect(onMessage).toHaveBeenCalledTimes(2);
    expect(onMessage).toHaveBeenNthCalledWith(1, {
      event: "plan_complete",
      data: { status: "done" },
    });
    expect(onMessage).toHaveBeenNthCalledWith(2, {
      event: "voice_summary",
      data: { text: "Paris" },
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it("does NOT call onError for a successful 2xx response", async () => {
    const sseChunk = "event: voice_summary\ndata: {\"summary\": \"Paris trip\"}\n\n";

    vi.stubGlobal("fetch", mockFetch200(makeStream(sseChunk)));

    const onError = vi.fn();
    const onMessage = vi.fn();

    const stop = openSSE("/api/trips/plan", { onMessage, onError });

    await new Promise<void>((resolve) => setTimeout(resolve, 50));
    stop();

    expect(onError).not.toHaveBeenCalled();
  });
});
