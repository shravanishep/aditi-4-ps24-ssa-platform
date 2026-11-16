/**
 * TypeScript types for Layer 8 ML Anomaly Detection (ADITI 4.0 v3).
 */

export interface RegimeThresholdInfo {
  warning_threshold: number
  critical_threshold: number
  decision_threshold: number
  validation_p90?: number
  validation_p95?: number
  notes?: string
}

export interface RegimeSummaryInfo {
  regime: 'LEO' | 'MEO' | 'GEO' | 'HEO'
  satellite_count: number
  observation_count: number
  warning_threshold: number
  critical_threshold: number
}

export interface MLModelStatusResponse {
  model_name: string
  model_version: string
  architecture: string
  dataset_version: string
  dataset_rows: number
  satellites_total: number
  training_split_satellites: number
  supported_regimes: string[]
  features_used: string[]
  feature_count: number
  loading_status: 'loaded' | 'unavailable' | 'error'
  trained_timestamp: string
  thresholds: Record<string, RegimeThresholdInfo>
  regime_summaries: RegimeSummaryInfo[]
}

export interface OfflineRegimeMetric {
  regime: 'LEO' | 'MEO' | 'GEO' | 'HEO'
  roc_auc: number
  recall: number
  precision: number
  f1_score: number
  false_alarm_rate: number
  unseen_alert_rate: number
}

export interface MLOfflineMetricsResponse {
  is_offline_benchmark: boolean
  disclaimer: string
  overall_test_roc_auc: number
  overall_test_recall: number
  overall_test_precision: number
  overall_test_f1: number
  overall_test_far: number
  unseen_satellites_evaluated: number
  unseen_alert_rate_overall: number
  regime_metrics: OfflineRegimeMetric[]
}

export interface AnomalyObservation {
  norad_id: number
  object_name: string
  regime: 'LEO' | 'MEO' | 'GEO' | 'HEO'
  observation_utc: string
  anomaly_score: number
  raw_decision_score?: number
  threshold_crossed: number
  severity: 'NORMAL' | 'WARNING' | 'CRITICAL'
  is_anomaly: boolean
  regime_model_used: string
  altitude_km: number
  speed_km_s: number
  specific_energy_km2_s2: number
  d_altitude_km: number
  d_speed_km_s: number
  d_specific_energy_km2_s2: number
  notes: string
}

export interface MLAnomaliesOverviewResponse {
  model_version: string
  total_evaluated_objects: number
  total_observations_evaluated: number
  normal_count: number
  warning_count: number
  critical_count: number
  score_distribution: {
    mean: number
    median: number
    p75: number
    p95: number
    min: number
    max: number
  }
  alerts_by_regime: Record<string, { normal: number; warning: number; critical: number }>
  recent_anomalies: AnomalyObservation[]
}
