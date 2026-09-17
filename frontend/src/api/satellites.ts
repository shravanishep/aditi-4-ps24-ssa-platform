import apiFetch from './client'
import type {
  SatelliteBasicInfo,
  SatelliteGPInfo,
  PropagatedOrbitStateResponse,
} from '../types/api'

/** Fetch a limited list of satellites from the GP dataset. */
export const listSatellites = (limit = 100): Promise<SatelliteBasicInfo[]> =>
  apiFetch<SatelliteBasicInfo[]>(`/satellites?limit=${limit}`)

/** Fetch the full GP orbital record for one NORAD catalog ID. */
export const getSatellite = (noradId: number): Promise<SatelliteGPInfo> =>
  apiFetch<SatelliteGPInfo>(`/satellites/${noradId}`)

/**
 * Propagate a satellite to a requested UTC timestamp.
 * @param timestamp ISO-8601 UTC string, e.g. "2026-09-20T10:00:00Z"
 */
export const getOrbit = (
  noradId: number,
  timestamp: string,
): Promise<PropagatedOrbitStateResponse> =>
  apiFetch<PropagatedOrbitStateResponse>(
    `/satellites/${noradId}/orbit?timestamp=${encodeURIComponent(timestamp)}`,
  )
