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
      <h1 className="text-xl font-bold text-slate-100 mb-1">Conjunction Analysis</h1>
      <p className="text-slate-400 text-sm mb-1">
        Find the approximate Time of Closest Approach between two orbital objects using SGP4 propagation.
      </p>
      <p className="text-xs text-slate-600 mb-6">
        Analytical prototype based on public orbital data. Not an operational collision-avoidance system.
      </p>

      {/* Form */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 mb-6">
        <ConjunctionForm onSubmit={handleSubmit} loading={loading} />
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-3 text-slate-400 text-sm mb-6">
          <LoadingSpinner size="sm" />
          <span>Running conjunction analysis… this may take several seconds.</span>
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
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
          <ConjunctionResult data={result} />
        </div>
      )}
    </div>
  )
}
