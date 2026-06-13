/**
 * SSE (Server-Sent Events) client helper.
 * Wraps the native EventSource with auth headers via a fetch-based polyfill
 * and handles reconnection + cleanup.
 */
import { getAccessToken } from "@/lib/auth";

const BASE_URL =
  typeof window !== "undefined"
    ? "" // browser: relative URLs go through the Next.js /api proxy rewrite
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"); // SSR

export interface SSEMessage {
  event: string;
  data: unknown;
}

export interface SSEOptions {
  onMessage: (msg: SSEMessage) => void;
  onError?: (err: Event | Error) => void;
  onOpen?: () => void;
}

/**
 * Opens an authenticated SSE connection to `path`.
 * Returns a cleanup function — call it to close the stream.
 *
 * Example:
 *   const stop = openSSE("/api/trips/plan", { onMessage: handleEvent });
 *   // later…
 *   stop();
 */
export function openSSE(path: string, options: SSEOptions): () => void {
  const { onMessage, onError, onOpen } = options;
  let aborted = false;
  let controller: AbortController | null = null;

  async function connect() {
    controller = new AbortController();
    const { signal } = controller;

    try {
      const token = await getAccessToken();
      const headers: Record<string, string> = {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const response = await fetch(`${BASE_URL}${path}`, {
        headers,
        signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`SSE connection failed: HTTP ${response.status}`);
      }

      onOpen?.();

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "message";
      let currentData = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done || aborted) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            currentData = line.slice(5).trim();
          } else if (line.trim() === "") {
            if (currentData) {
              let parsed: unknown = currentData;
              try { parsed = JSON.parse(currentData); } catch { /* keep as string */ }
              onMessage({ event: currentEvent, data: parsed });
              currentEvent = "message";
              currentData = "";
            }
          }
        }
      }
    } catch (err) {
      if (aborted) return;
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  }

  connect();

  return () => {
    aborted = true;
    controller?.abort();
  };
}

/**
 * Opens an SSE stream for a POST body (trip planning).
 * The `body` is serialised as JSON and sent as a regular fetch POST;
 * the response streams SSE events.
 */
export function postSSE(
  path: string,
  body: unknown,
  options: SSEOptions
): () => void {
  const { onMessage, onError, onOpen } = options;
  let aborted = false;
  let controller: AbortController | null = null;

  async function connect() {
    controller = new AbortController();
    const { signal } = controller;

    try {
      const token = await getAccessToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const response = await fetch(`${BASE_URL}${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`SSE POST failed: HTTP ${response.status}`);
      }

      onOpen?.();

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "message";
      let currentData = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done || aborted) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            currentData = line.slice(5).trim();
          } else if (line.trim() === "") {
            if (currentData) {
              let parsed: unknown = currentData;
              try { parsed = JSON.parse(currentData); } catch { /* keep as string */ }
              onMessage({ event: currentEvent, data: parsed });
              currentEvent = "message";
              currentData = "";
            }
          }
        }
      }
    } catch (err) {
      if (aborted) return;
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  }

  connect();

  return () => {
    aborted = true;
    controller?.abort();
  };
}
