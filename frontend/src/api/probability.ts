import apiFetch from './client'
import type {
  CDMParseRequest,
  CDMParseResponse,
  PcComputeRequest,
  PcComputeResponse,
  PcFromCDMRequest,
  PcFromCDMResponse,
} from '../types/api'

/**
 * Parse raw CDM text content into structured fields.
 */
export const parseCDM = (req: CDMParseRequest): Promise<CDMParseResponse> =>
  apiFetch<CDMParseResponse>('/cdm/parse', {
    method: 'POST',
    body: JSON.stringify(req),
  })

/**
 * Compute Foster 2-D collision probability from miss distance, speed, and covariance.
 */
export const computePc = (req: PcComputeRequest): Promise<PcComputeResponse> =>
  apiFetch<PcComputeResponse>('/pc/compute', {
    method: 'POST',
    body: JSON.stringify(req),
  })

/**
 * Parse CDM and evaluate collision probability in a single request.
 */
export const computePcFromCDM = (req: PcFromCDMRequest): Promise<PcFromCDMResponse> =>
  apiFetch<PcFromCDMResponse>('/pc/from-cdm', {
    method: 'POST',
    body: JSON.stringify(req),
  })

/**
 * Get scientific documentation and methodology notes for Foster 2-D calculation.
 */
export const getPcMethodInfo = (): Promise<{
  method: string
  description: string
  assumptions: string[]
  covariance_requirement: string
  disclaimer: string
}> => apiFetch('/pc/method-info')

