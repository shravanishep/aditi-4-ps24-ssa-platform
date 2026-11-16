import apiFetch from './client'
import type {
  MLModelStatusResponse,
  MLOfflineMetricsResponse,
  MLAnomaliesOverviewResponse,
  AnomalyObservation,
} from '../types/ml'

export async function getMLStatus(): Promise<MLModelStatusResponse> {
  return apiFetch<MLModelStatusResponse>('/ml/status')
}

export async function getMLMetrics(): Promise<MLOfflineMetricsResponse> {
  return apiFetch<MLOfflineMetricsResponse>('/ml/metrics')
}

export async function getMLAnomalies(limit = 40): Promise<MLAnomaliesOverviewResponse> {
  return apiFetch<MLAnomaliesOverviewResponse>(`/ml/anomalies?limit=${limit}`)
}

export async function getSatelliteAnomaly(noradId: number): Promise<AnomalyObservation> {
  return apiFetch<AnomalyObservation>(`/ml/anomalies/${noradId}`)
}
