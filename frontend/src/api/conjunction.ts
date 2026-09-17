import apiFetch from './client'
import type {
  ConjunctionAnalysisRequest,
  CloseApproachResultResponse,
} from '../types/api'

/**
 * Run a conjunction / close-approach analysis via Layer 3.
 * All orbital computation happens in the Python backend.
 */
export const analyzeConjunction = (
  req: ConjunctionAnalysisRequest,
): Promise<CloseApproachResultResponse> =>
  apiFetch<CloseApproachResultResponse>('/conjunction/analyze', {
    method: 'POST',
    body: JSON.stringify(req),
  })
