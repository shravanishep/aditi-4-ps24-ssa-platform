import apiFetch from './client'
import type { CatalogStatusResponse } from '../types/api'

/**
 * Fetch current catalogue freshness and automated refresh metadata.
 */
export async function getCatalogStatus(): Promise<CatalogStatusResponse> {
  return apiFetch<CatalogStatusResponse>('/catalog/status')
}
