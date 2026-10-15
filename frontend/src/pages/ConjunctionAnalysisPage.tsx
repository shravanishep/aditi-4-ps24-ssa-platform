import { useState } from 'react'
import { analyzeConjunction } from '../api/conjunction'
import { ApiError } from '../api/client'
import type { CloseApproachResultResponse, ConjunctionAnalysisRequest } from '../types/api'
import ConjunctionForm from '../components/conjunction/ConjunctionForm'
import ConjunctionResult from '../components/conjunction/ConjunctionResult'
import LoadingSpinner from '../components/common/LoadingSpinner'
import ErrorMessage from '../components/common/ErrorMessage'

export default function ConjunctionAnalysisPage() {
  const [result, setResult] = useState<CloseApproachResultResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(req: ConjunctionAnalysisRequest) {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await analyzeConjunction(req)
      setResult(data)
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Unexpected error during analysis.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-2xl font-bold text-slate-100 mb-1">Conjunction Analysis</h1>
      <p className="text-slate-400 text-sm mb-4">
        Calculate approximate Time of Closest Approach (TCA) and miss distance between two orbital objects using SGP4 propagation.
      </p>

      {/* Neutral informational notice */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-lg p-3.5 mb-6 flex items-start gap-3 text-xs text-slate-300">
        <span className="text-cyan-400 font-bold text-sm leading-none mt-0.5">ℹ</span>
        <div>
          <span className="font-semibold text-slate-200">Advisory Research Prototype: </span>
          <span>
            Research prototype using public orbital data. Results are advisory and are not operational collision-avoidance guidance. Close approaches reflect analytical geometry, not physical collision probability.
          </span>
        </div>
      </div>

      {/* Form */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 mb-6">
        <ConjunctionForm onSubmit={handleSubmit} loading={loading} />
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-3 text-slate-400 text-sm mb-6 bg-slate-800/50 p-4 rounded-lg border border-slate-700">
          <LoadingSpinner size="sm" />
          <span>Propagating orbital trajectories and searching for closest approach…</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-6">
          <ErrorMessage message={error} />
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
          <ConjunctionResult data={result} />
        </div>
      )}
    </div>
  )
}
