/**
 * TypeScript interfaces mirroring the Layer 4 FastAPI Pydantic schemas exactly.
 * Do not add computed fields or perform orbital math here.
 * All computation happens in the Python backend.
 */

export interface SatelliteBasicInfo {
  norad_cat_id: number
  object_name: string
}

export interface SatelliteGPInfo extends SatelliteBasicInfo {
  object_id: string | null
  epoch: string
  mean_motion: number
  eccentricity: number
  inclination: number
  ra_of_asc_node: number
  arg_of_pericenter: number
  mean_anomaly: number
  bstar: number
  mean_motion_dot: number
  mean_motion_ddot: number
}

/** Position in km (TEME frame), velocity in km/s. */
export interface PropagatedOrbitStateResponse {
  object_name: string
  norad_cat_id: number
  timestamp: string
  position_x_km: number
  position_y_km: number
  position_z_km: number
  velocity_x_km_s: number
  velocity_y_km_s: number
  velocity_z_km_s: number
  sgp4_error: number
  error_message: string
}

export interface ConjunctionAnalysisRequest {
  norad1: number
  norad2: number
  /** ISO-8601 with timezone, e.g. 2026-09-20T10:00:00Z */
  start_time: string
  /** ISO-8601 with timezone, e.g. 2026-09-20T12:00:00Z */
  end_time: string
  threshold_km: number
  coarse_step_sec?: number
  fine_step_sec?: number
}

/**
 * Analytical close-approach result.
 * Distances in km, speeds in km/s.
 * NOT a collision probability or operational collision-avoidance output.
 */
export interface CloseApproachResultResponse {
  object1_norad_id: number
  object2_norad_id: number
  object1_name: string
  object2_name: string
  analysis_start_time: string
  analysis_end_time: string
  time_of_closest_approach: string
  minimum_separation_km: number
  relative_speed_km_s: number
  threshold_km: number
  is_candidate_close_approach: boolean
  error_message: string
}
