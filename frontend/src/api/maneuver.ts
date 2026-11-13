import apiFetch from './client'
import type {
  ManeuverSimulationRequest,
  ManeuverSimulationResponse,
} from '../types/api'

/**
 * Simulate an impulsive velocity change (CAM) for a protected satellite.
 * Computation is performed via numerical two-body + J2 integration in the backend.
 */
export const simulateManeuver = (
  req: ManeuverSimulationRequest,
): Promise<ManeuverSimulationResponse> =>
  apiFetch<ManeuverSimulationResponse>('/maneuver/simulate', {
    method: 'POST',
    body: JSON.stringify(req),
    timeoutMs: 90000,
  })

