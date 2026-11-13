import { useState } from 'react'
import { analyzeConjunction } from '../api/conjunction'
import { ApiError } from '../api/client'
import type { CloseApproachResultResponse, ConjunctionAnalysisRequest } from '../types/api'
import ConjunctionForm from '../components/conjunction/ConjunctionForm'
import ConjunctionResult from '../components/conjunction/ConjunctionResult'
import ManeuverSimulator from '../components/conjunction/ManeuverSimulator'
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
        err instanceof ApiError ? err.message : 'Unexpected error during conjunction analysis.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <span className="text-sky-400 font-mono text-lg">⚡</span> Conjunction Analysis & Collision Avoidance
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Calculate approximate Time of Closest Approach (TCA), relative geometry, and geometric miss distance between orbital pairs using SGP4 analytical propagation.
        </p>
      </div>

      {/* Advisory Banner */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-lg p-3.5 mb-6 flex items-start gap-3 text-xs text-slate-300">
        <span className="text-sky-400 font-bold text-sm leading-none mt-0.5">ℹ</span>
        <div className="space-y-1">
          <span className="font-semibold text-slate-200">Analytical Geometry Notice: </span>
          <span className="text-slate-400 leading-relaxed">
            A detected conjunction represents a geometric close approach evaluated from public two-line element (TLE) sets. It indicates spatial proximity during the evaluation window and is NOT a confirmed physical collision. Operational avoidance decisions require high-accuracy covariance and radar tracking.
          </span>
        </div>
      </div>

      {/* Primary Section 1: Conjunction Screening Form */}
      <section className="bg-slate-800 border border-slate-700 rounded-lg p-6 mb-6">
        <h2 className="text-sm font-semibold text-slate-200 mb-4 border-b border-slate-700 pb-2">
          1. Select Orbital Pair & Evaluation Window
        </h2>
        <ConjunctionForm onSubmit={handleSubmit} loading={loading} />
      </section>

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-3 text-slate-400 text-sm mb-6 bg-slate-800/50 p-4 rounded-lg border border-slate-700">
          <LoadingSpinner size="sm" />
          <span>Propagating orbital trajectories and executing bisection search for closest approach…</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-6">
          <ErrorMessage message={error} />
        </div>
      )}

      {/* Result Section */}
      {result && (
        <div className="space-y-6">
          {/* Section 2: Conjunction Result */}
          <section className="bg-slate-800 border border-slate-700 rounded-lg p-6">
            <h2 className="text-sm font-semibold text-slate-200 mb-4 border-b border-slate-700 pb-2">
              2. Encounter Evaluation Summary
            </h2>
            <ConjunctionResult data={result} />
          </section>

          {/* Section 3: Collision Avoidance Maneuver (CAM) Simulator */}
          <section>
            <ManeuverSimulator
              norad1={result.object1_norad_id}
              norad2={result.object2_norad_id}
              satellite1Name={result.object1_name}
              satellite2Name={result.object2_name}
              defaultManeuverTime={result.time_of_closest_approach}
              windowStart={result.analysis_start_time}
              windowEnd={result.analysis_end_time}
              tca={result.time_of_closest_approach}
            />
          </section>
        </div>
      )}
    </div>
  )
}
