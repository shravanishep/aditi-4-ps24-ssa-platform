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

export interface MultiPropagateParams {
  timestamp?: string
  limit?: number
  offset?: number
  category?: string
  regime?: string
  search?: string
  noradIds?: string
}

/**
 * Propagate a bounded set of catalogue objects to a specific UTC epoch.
 */
export const multiPropagateSatellites = (
  params?: MultiPropagateParams,
): Promise<import('../types/api').MultiPropagatedOrbitResponse> => {
  const query = new URLSearchParams()
  if (params?.timestamp) query.set('target_time', params.timestamp)
  if (params?.limit) query.set('limit', params.limit.toString())
  if (params?.offset) query.set('offset', params.offset.toString())
  if (params?.category) query.set('category', params.category)
  if (params?.regime) query.set('regime', params.regime)
  if (params?.search) query.set('search', params.search)
  if (params?.noradIds) query.set('norad_ids', params.noradIds)
  const qs = query.toString()
  return apiFetch<import('../types/api').MultiPropagatedOrbitResponse>(
    `/satellites/multi-propagate${qs ? `?${qs}` : ''}`,
  )
}
