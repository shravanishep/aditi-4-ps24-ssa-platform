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

/** One SGP4-propagated state in a trajectory sequence.
 *  Position in km (TEME frame), velocity in km/s.
 *  Points where sgp4_error !== 0 indicate SGP4 failure at that step.
 */
export interface TrajectoryPointResponse {
  timestamp: string // UTC ISO-8601
  position_x_km: number
  position_y_km: number
  position_z_km: number
  velocity_x_km_s: number
  velocity_y_km_s: number
  velocity_z_km_s: number
  sgp4_error: number
}

/** Multi-point trajectory. frame is always "TEME".
 *  The frontend must apply Cesium.Transforms.computeTemeToPseudoFixedMatrix()
 *  before rendering positions on the globe.
 */
export interface TrajectoryResponse {
  norad_cat_id: number
  object_name: string
  frame: string
  step_sec: number
  points: TrajectoryPointResponse[]
}

/**
 * Layer 11 Threat Prioritization interfaces
 */

export interface ThreatFactorItem {
  description: string
  raw_value_km?: number
  raw_value_km_s?: number
  raw_value_hours?: number
  raw_value?: number | string
  normalised: number
  weight: number
  contribution: number
}

export interface ThreatFactorBreakdown {
  risk_score: number
  risk_severity: 'critical' | 'warning' | 'low'
  anomaly_data_available: boolean
  factors: {
    separation?: ThreatFactorItem
    relative_velocity?: ThreatFactorItem
    time_to_tca?: ThreatFactorItem
    anomaly_score?: ThreatFactorItem
    [key: string]: ThreatFactorItem | undefined
  }
  disclaimer?: string
}

export interface ThreatEvent {
  protected_norad_id: number
  protected_name: string
  protected_classification: string
  threat_norad_id: number
  threat_name: string
  threat_classification: string
  threat_source_provenance: string
  time_of_closest_approach: string
  minimum_separation_km: number
  relative_speed_km_s: number
  hours_to_tca: number
  threat_anomaly_score: number | null
  threat_anomaly_severity: string
  risk_score: number
  risk_severity: 'critical' | 'warning' | 'low'
  risk_explanation: ThreatFactorBreakdown
  screening_notes: string[]
}

export interface ThreatScreeningSummary {
  protected_count: number
  candidates_screened: number
  pairs_evaluated: number
  events_within_threshold: number
  data_source_notes: string[]
  config_summary: Record<string, unknown>
  disclaimer: string
}

export interface ThreatScreeningResponse {
  events: ThreatEvent[]
  summary: ThreatScreeningSummary
}

export interface ThreatScreeningRequest {
  protected_norad_ids?: number[]
  protect_all_active?: boolean
  max_protected_targets?: number
  screening_threshold_km?: number
  screening_window_hours?: number
  max_threat_candidates?: number
  max_ranked_results?: number
  coarse_step_sec?: number
  fine_step_sec?: number
  max_epoch_age_days?: number
  stale_data_policy?: 'flag' | 'exclude'
}
