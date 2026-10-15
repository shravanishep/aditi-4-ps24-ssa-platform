import apiFetch from './client'
import type { ThreatScreeningRequest, ThreatScreeningResponse } from '../types/api'

/**
 * Call the Layer 11 threat screening endpoint.
 *
 * All scoring and SGP4 conjunction evaluation takes place in the backend.
 * Returns ranked candidate threat events with contributing factors.
 */
export async function screenThreats(
  params?: ThreatScreeningRequest,
  timeoutMs = 90000,
): Promise<ThreatScreeningResponse> {
  return apiFetch<ThreatScreeningResponse>('/threats/screen', {
    method: 'POST',
    body: JSON.stringify(params ?? {}),
    timeoutMs,
  })
}
