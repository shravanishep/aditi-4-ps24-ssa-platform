/// <reference types="vite/client" />

/**
 * Base API fetch wrapper.
 *
 * All HTTP calls in the application go through apiFetch().
 * Components and pages must NOT call fetch() directly.
 *
 * In development the Vite proxy routes /health, /satellites, and /conjunction
 * to http://localhost:8000, so VITE_API_BASE_URL should be left empty.
 *
 * In production set VITE_API_BASE_URL to the deployed backend origin.
 */

const BASE: string = import.meta.env.VITE_API_BASE_URL ?? ''

/** Typed API error that carries the HTTP status code. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const timeoutMs = options?.timeoutMs ?? 60000
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  let response: Response

  try {
    response = await fetch(`${BASE}${path}`, {
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch (err: unknown) {
    clearTimeout(timer)
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError(
        408,
        `Request timed out after ${timeoutMs / 1000}s — server took too long to complete calculation.`,
      )
    }
    throw new ApiError(
      0,
      'Backend unavailable — ensure the FastAPI server is running on port 8000.',
    )
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (body.detail !== undefined) {
        detail =
          typeof body.detail === 'string'
            ? body.detail
            : JSON.stringify(body.detail)
      }
    } catch {
      /* ignore JSON parse failure — use the default status message */
    }
    throw new ApiError(response.status, detail)
  }

  return response.json() as Promise<T>
}

export default apiFetch
