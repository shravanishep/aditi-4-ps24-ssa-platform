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

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new ApiError(
      0,
      'Backend unavailable — ensure the FastAPI server is running on port 8000.',
    )
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
