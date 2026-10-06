import apiFetch from './client'
import type { TrajectoryResponse } from '../types/api'

/**
 * Fetch a multi-point trajectory sequence for one satellite.
 * Points are in the TEME reference frame and must be transformed
 * to the Earth-fixed frame before 3D globe rendering.
 *
 * @param noradId NORAD catalog ID
 * @param start UTC ISO-8601 string, e.g. "2026-09-17T12:00:00Z"
 * @param end UTC ISO-8601 string, e.g. "2026-09-17T13:00:00Z"
 * @param stepSec Sampling interval in seconds (default: 60.0)
 */
export const getTrajectory = (
  noradId: number,
  start: string,
  end: string,
  stepSec: number = 60.0,
): Promise<TrajectoryResponse> =>
  apiFetch<TrajectoryResponse>(
    `/satellites/${noradId}/trajectory?` +
      `start=${encodeURIComponent(start)}` +
      `&end=${encodeURIComponent(end)}` +
      `&step_sec=${stepSec}`,
  )
