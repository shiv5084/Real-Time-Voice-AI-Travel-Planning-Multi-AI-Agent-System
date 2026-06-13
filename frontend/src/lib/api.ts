/**
 * API client — typed fetch wrapper that injects auth headers
 * and points at NEXT_PUBLIC_API_URL (or the /api rewrite in dev).
 */
import { getAccessToken } from "@/lib/auth";

const BASE_URL =
  typeof window !== "undefined"
    ? "" // browser: relative URLs go through the Next.js /api proxy rewrite
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"); // SSR

// ── Core fetch helper ────────────────────────────────────────────────────

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** If true, skip the Authorization header (e.g. login/register). */
  unauthenticated?: boolean;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, unauthenticated, ...rest } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((rest.headers ?? {}) as Record<string, string>),
  };

  if (!unauthenticated) {
    const token = await getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  // Use a 10-minute timeout for pipeline plan calls and 3-minute timeout for other calls.
  // The LangGraph pipeline can legitimately take 2–3 minutes, especially under fallback conditions.
  const controller = new AbortController();
  const timeoutMs = path.includes("/trips/plan") ? 10 * 60 * 1000 : 3 * 60 * 1000;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const err = await response.json();
        message = err?.detail ?? err?.message ?? message;
      } catch {
        // ignore parse error
      }
      throw new Error(message);
    }

    // 204 No Content
    if (response.status === 204) return undefined as T;

    return response.json() as Promise<T>;
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error("Request timed out — the server is taking too long. Please try again.");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ── Convenience wrappers ─────────────────────────────────────────────────

export const api = {
  get: <T>(path: string, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "GET", ...opts }),

  post: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "POST", body, ...opts }),

  put: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "PUT", body, ...opts }),

  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "PATCH", body, ...opts }),

  delete: <T>(path: string, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "DELETE", ...opts }),
};

// ── Blob download ────────────────────────────────────────────────────────

/**
 * Download a binary endpoint (e.g. PDF) and trigger a browser download.
 */
export async function downloadFile(
  path: string,
  filename: string,
  unauthenticated: boolean = false
): Promise<void> {
  const headers: Record<string, string> = {};
  if (!unauthenticated) {
    const token = await getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, { headers });
  if (!response.ok) throw new Error(`Download failed: HTTP ${response.status}`);

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
