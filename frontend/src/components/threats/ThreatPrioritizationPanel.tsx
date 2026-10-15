import { useState } from 'react'
import { screenThreats } from '../../api/threats'
import type { ThreatEvent, ThreatScreeningResponse, ThreatScreeningRequest } from '../../types/api'
import LoadingSpinner from '../common/LoadingSpinner'

export default function ThreatPrioritizationPanel() {
  const [data, setData] = useState<ThreatScreeningResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null)

  // User screening controls
  const [thresholdKm, setThresholdKm] = useState<number>(50.0)
  const [maxCandidates, setMaxCandidates] = useState<number>(10)
  const [protectedCount, setProtectedCount] = useState<number>(2)
  const [windowHours, setWindowHours] = useState<number>(24.0)
  const [stalePolicy, setStalePolicy] = useState<'flag' | 'exclude'>('flag')

  const fetchThreats = (params?: Partial<ThreatScreeningRequest>) => {
    setLoading(true)
    setError(null)

    const req: ThreatScreeningRequest = {
      screening_threshold_km: params?.screening_threshold_km ?? thresholdKm,
      max_threat_candidates: params?.max_threat_candidates ?? maxCandidates,
      max_protected_targets: params?.max_protected_targets ?? protectedCount,
      screening_window_hours: params?.screening_window_hours ?? windowHours,
      stale_data_policy: params?.stale_data_policy ?? stalePolicy,
      coarse_step_sec: 120.0,
      fine_step_sec: 1.0,
    }

    screenThreats(req, 90000)
      .then((res) => {
        setData(res)
        setError(null)
      })
      .catch((err: Error) => {
        setError(err.message || 'Failed to screen catalogue threats.')
      })
      .finally(() => {
        setLoading(false)
      })
  }

  const handleRefresh = () => {
    fetchThreats()
  }

  const toggleExpand = (idx: number) => {
    setExpandedIndex(expandedIndex === idx ? null : idx)
  }

  const getSeverityBadge = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 'bg-red-950 text-red-300 border-red-700'
      case 'warning':
        return 'bg-amber-950 text-amber-300 border-amber-700'
      default:
        return 'bg-slate-700 text-slate-300 border-slate-600'
    }
  }

  const getClassificationBadge = (classification: string) => {
    switch (classification.toUpperCase()) {
      case 'ACTIVE_SATELLITE':
        return 'bg-cyan-950 text-cyan-300 border-cyan-800'
      case 'INACTIVE_SATELLITE':
        return 'bg-purple-950 text-purple-300 border-purple-800'
      case 'ROCKET_BODY':
        return 'bg-orange-950 text-orange-300 border-orange-800'
      case 'DEBRIS':
        return 'bg-rose-950 text-rose-300 border-rose-800'
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700'
    }
  }

  const highPriorityCount = data?.events.filter((e) => e.risk_severity.toLowerCase() === 'critical').length ?? 0
  const topEvent = data?.events && data.events.length > 0 ? data.events[0] : null

  return (
    <section className="bg-slate-800 border border-slate-700 rounded-lg p-6 mb-8" id="threat-prioritization-panel">
      {/* Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span>Threat Prioritization & Screening</span>
            <span className="text-xs font-normal text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-700">
              Layer 9 · Layer 10
            </span>
          </h2>
          <p className="text-slate-400 text-xs mt-1">
            Catalogue-wide close-approach ranking using analytical SGP4 propagation and heuristic scoring.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-700 text-white rounded text-xs font-semibold transition-colors flex items-center gap-2 cursor-pointer disabled:cursor-not-allowed shadow"
          >
            {loading ? <LoadingSpinner size="sm" /> : <span>↻</span>}
            <span>{loading ? 'Screening In Progress…' : 'Run Threat Screening'}</span>
          </button>
        </div>
      </div>

      {/* Heuristic Prioritization Disclaimer Banner */}
      <div className="mb-5 bg-amber-950/40 border border-amber-700/60 rounded-md p-3 text-xs text-amber-200/90 leading-relaxed">
        <p className="font-semibold flex items-center gap-1.5 text-amber-300 mb-0.5">
          <span>ℹ</span>
          <span>Heuristic Prioritization Index — Not Collision Probability (Pc)</span>
        </p>
        <p>
          Calculated threat scores are ranking indicators derived from analytical SGP4 miss distance,
          relative velocity, and time-to-closest-approach. They represent operational screening priority,
          NOT validated physical collision probability. Conjunction events do not imply confirmed collisions.
        </p>
      </div>

      {/* Screening Controls */}
      <div className="bg-slate-900 border border-slate-700/80 rounded-md p-3.5 mb-5 flex flex-wrap items-center gap-4 text-xs">
        <div className="flex items-center gap-2">
          <label htmlFor="threat-threshold" className="text-slate-400 font-medium">
            Threshold (km):
          </label>
          <input
            id="threat-threshold"
            type="number"
            min="1"
            max="500"
            step="5"
            value={thresholdKm}
            onChange={(e) => setThresholdKm(Math.max(1, parseFloat(e.target.value) || 1))}
            className="w-20 bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
          />
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="threat-targets" className="text-slate-400 font-medium">
            Targets:
          </label>
          <select
            id="threat-targets"
            value={protectedCount}
            onChange={(e) => setProtectedCount(parseInt(e.target.value, 10))}
            className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="2">2 targets (Fast · ~5s)</option>
            <option value="5">5 targets (Standard · ~15s)</option>
            <option value="10">10 targets (Extended · ~30s)</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="threat-candidates" className="text-slate-400 font-medium">
            Candidates:
          </label>
          <select
            id="threat-candidates"
            value={maxCandidates}
            onChange={(e) => setMaxCandidates(parseInt(e.target.value, 10))}
            className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="5">5 objects</option>
            <option value="10">10 objects</option>
            <option value="20">20 objects</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="threat-window" className="text-slate-400 font-medium">
            Window:
          </label>
          <select
            id="threat-window"
            value={windowHours}
            onChange={(e) => setWindowHours(parseFloat(e.target.value))}
            className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="12">12 hours</option>
            <option value="24">24 hours</option>
            <option value="48">48 hours</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="threat-stale-policy" className="text-slate-400 font-medium">
            Stale Data:
          </label>
          <select
            id="threat-stale-policy"
            value={stalePolicy}
            onChange={(e) => setStalePolicy(e.target.value as 'flag' | 'exclude')}
            className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="flag">Flag with warning</option>
            <option value="exclude">Exclude stale</option>
          </select>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-950/80 border border-red-700 rounded-md p-4 mb-4 text-sm text-red-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <p className="font-semibold">Threat screening request failed</p>
            <p className="text-xs text-red-300 mt-0.5">{error}</p>
          </div>
          <button
            onClick={handleRefresh}
            className="px-3 py-1 bg-red-800 hover:bg-red-700 rounded text-xs text-white transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading state indicator */}
      {loading && (
        <div className="py-8 flex flex-col items-center justify-center gap-3 text-slate-300 text-xs bg-slate-900/60 rounded-lg border border-slate-700/80 mb-4">
          <LoadingSpinner size="md" />
          <span className="font-semibold text-slate-200">
            Evaluating SGP4 Conjunctions & Computing Prioritization Scores…
          </span>
          <span className="text-slate-400 text-[11px]">
            Evaluating {protectedCount} protected targets against {maxCandidates} candidate orbits across {windowHours}h window.
          </span>
        </div>
      )}

      {/* Initial Ready State when screening has not run yet */}
      {!loading && !data && !error && (
        <div className="bg-slate-900/40 border border-slate-700/60 rounded-lg p-6 text-center text-xs text-slate-400 space-y-3">
          <p className="text-slate-300 font-medium">
            Screening parameters configured. Ready to evaluate close approach encounters.
          </p>
          <p className="text-slate-500 text-[11px] max-w-xl mx-auto">
            Click <strong className="text-cyan-400">Run Threat Screening</strong> above to initiate analytical SGP4 propagation and rank potential conjunctions by geometric miss distance and relative velocity.
          </p>
        </div>
      )}

      {/* Results content */}
      {!loading && data && (
        <div>
          {/* Summary Stats Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
            <div className="bg-slate-900 border border-slate-700 rounded p-2.5">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block">
                Protected Targets
              </span>
              <span className="text-lg font-mono font-semibold text-cyan-400">
                {data.summary.protected_count}
              </span>
            </div>
            <div className="bg-slate-900 border border-slate-700 rounded p-2.5">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block">
                Candidates Screened
              </span>
              <span className="text-lg font-mono font-semibold text-slate-200">
                {data.summary.candidates_screened}
              </span>
            </div>
            <div className="bg-slate-900 border border-slate-700 rounded p-2.5">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block">
                Pairs Evaluated
              </span>
              <span className="text-lg font-mono font-semibold text-slate-200">
                {data.summary.pairs_evaluated}
              </span>
            </div>
            <div className="bg-slate-900 border border-slate-700 rounded p-2.5">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block">
                Events Found
              </span>
              <span className="text-lg font-mono font-semibold text-amber-400">
                {data.summary.events_within_threshold}
              </span>
            </div>
            <div className="bg-slate-900 border border-slate-700 rounded p-2.5">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block">
                High Priority
              </span>
              <span className="text-lg font-mono font-semibold text-rose-400">
                {highPriorityCount}
              </span>
            </div>
          </div>

          {/* Top Priority Event Highlight Banner if any events */}
          {topEvent && (
            <div className="bg-slate-900/90 border border-cyan-800/80 rounded-lg p-4 mb-4">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <span className="text-xs font-semibold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                  <span>★</span>
                  <span>Highest Priority Threat Event</span>
                </span>
                <span
                  className={`text-xs px-2.5 py-0.5 rounded-full border font-semibold uppercase ${getSeverityBadge(
                    topEvent.risk_severity,
                  )}`}
                >
                  {topEvent.risk_severity} (Score {topEvent.risk_score.toFixed(3)})
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3 text-xs">
                <div>
                  <span className="text-slate-400 block text-[11px]">Encounter Pair</span>
                  <span className="font-semibold text-slate-100">{topEvent.protected_name}</span>
                  <span className="text-slate-400"> vs </span>
                  <span className="font-semibold text-slate-100">{topEvent.threat_name}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px]">Separation Distance</span>
                  <span className="font-mono font-bold text-amber-300">
                    {topEvent.minimum_separation_km.toFixed(2)} km
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px]">Time to TCA</span>
                  <span className="font-mono text-cyan-300">
                    {topEvent.hours_to_tca.toFixed(1)} hours
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Empty state */}
          {data.events.length === 0 ? (
            <div className="bg-slate-900/60 border border-slate-700 rounded-md p-8 text-center text-slate-400 text-sm">
              <p className="font-semibold text-slate-300 mb-1">
                No threat events within {thresholdKm.toFixed(1)} km threshold
              </p>
              <p className="text-xs text-slate-500">
                Screened {data.summary.pairs_evaluated} orbital pairs over the {windowHours}h propagation window.
                Try expanding the threshold distance or candidate limits.
              </p>
            </div>
          ) : (
            /* Events List */
            <div className="space-y-3">
              {data.events.map((event: ThreatEvent, index: number) => {
                const isExpanded = expandedIndex === index
                const hasStaleWarning = event.screening_notes.some((n) =>
                  n.includes('STALE ORBITAL DATA'),
                )
                const isUnverified =
                  event.threat_source_provenance.includes('hint') ||
                  event.threat_source_provenance.includes('no SATCAT')

                return (
                  <div
                    key={`${event.protected_norad_id}-${event.threat_norad_id}-${index}`}
                    className="bg-slate-900 border border-slate-700 rounded-lg p-4 transition-all hover:border-slate-600"
                  >
                    {/* Header: Rank, Names, Severity */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                          #{index + 1}
                        </span>

                        <span
                          className={`text-xs px-2.5 py-0.5 rounded-full border font-semibold uppercase tracking-wider ${getSeverityBadge(
                            event.risk_severity,
                          )}`}
                        >
                          {event.risk_severity} Priority
                        </span>

                        <span className="text-xs font-mono text-slate-300">
                          Score:{' '}
                          <span className="font-bold text-slate-100">
                            {event.risk_score.toFixed(3)}
                          </span>
                        </span>
                      </div>

                      {/* Warnings if any */}
                      <div className="flex items-center gap-2 flex-wrap">
                        {hasStaleWarning && (
                          <span className="text-[11px] px-2 py-0.5 bg-amber-950/80 border border-amber-700 text-amber-300 rounded font-medium">
                            ⚠ Stale Orbital Data
                          </span>
                        )}
                        {isUnverified && (
                          <span className="text-[11px] px-2 py-0.5 bg-slate-800 border border-slate-700 text-slate-400 rounded">
                            Unverified Classification
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Pair Information */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 my-3">
                      {/* Protected Satellite */}
                      <div className="bg-slate-800/80 border border-slate-700/60 rounded p-2.5">
                        <span className="text-[10px] text-slate-400 uppercase tracking-widest block mb-1">
                          Protected Target
                        </span>
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-slate-100">
                              {event.protected_name}
                            </p>
                            <p className="text-xs font-mono text-cyan-400">
                              NORAD {event.protected_norad_id}
                            </p>
                          </div>
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded border font-medium ${getClassificationBadge(
                              event.protected_classification,
                            )}`}
                          >
                            {event.protected_classification}
                          </span>
                        </div>
                      </div>

                      {/* Threat Object */}
                      <div className="bg-slate-800/80 border border-slate-700/60 rounded p-2.5">
                        <span className="text-[10px] text-slate-400 uppercase tracking-widest block mb-1">
                          Threatening Candidate
                        </span>
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-slate-100">
                              {event.threat_name}
                            </p>
                            <p className="text-xs font-mono text-rose-400">
                              NORAD {event.threat_norad_id}
                            </p>
                          </div>
                          <div className="text-right">
                            <span
                              className={`text-[10px] px-2 py-0.5 rounded border font-medium ${getClassificationBadge(
                                event.threat_classification,
                              )}`}
                            >
                              {event.threat_classification}
                            </span>
                            {event.threat_source_provenance && (
                              <p className="text-[10px] text-slate-400 mt-0.5">
                                {event.threat_source_provenance}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Conjunction Metrics Row */}
                    <div className="grid grid-cols-3 gap-2 bg-slate-800/50 rounded p-2 text-xs text-slate-300">
                      <div>
                        <span className="text-[10px] text-slate-400 block">Separation Distance</span>
                        <span className="font-mono font-bold text-amber-300">
                          {event.minimum_separation_km.toFixed(2)} km
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-400 block">Relative Velocity</span>
                        <span className="font-mono font-bold text-slate-100">
                          {event.relative_speed_km_s.toFixed(3)} km/s
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-400 block">Time to TCA</span>
                        <span className="font-mono text-cyan-300">
                          {event.hours_to_tca.toFixed(1)}h
                        </span>
                      </div>
                    </div>

                    {/* Stale data note alert */}
                    {event.screening_notes.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {event.screening_notes.map((note, noteIdx) => (
                          <div
                            key={noteIdx}
                            className="text-[11px] bg-amber-950/40 border border-amber-800/50 rounded px-2 py-1 text-amber-300 font-mono"
                          >
                            {note}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Factor Breakdown Toggle */}
                    <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between">
                      <span className="text-[11px] text-slate-400">
                        Closest Approach:{' '}
                        <span className="font-mono text-slate-300">
                          {new Date(event.time_of_closest_approach).toISOString()}
                        </span>
                      </span>

                      <button
                        onClick={() => toggleExpand(index)}
                        className="text-xs text-cyan-400 hover:text-cyan-300 font-medium flex items-center gap-1 transition-colors"
                      >
                        <span>{isExpanded ? 'Hide Factors ▲' : 'Inspect Contributing Factors ▼'}</span>
                      </button>
                    </div>

                    {/* Expanded Factor Details */}
                    {isExpanded && event.risk_explanation?.factors && (
                      <div className="mt-3 p-3 bg-slate-950/70 border border-slate-800 rounded-md space-y-2 text-xs">
                        <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                          Risk Priority Factor Decomposition
                        </p>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-300">
                          {/* Separation */}
                          {event.risk_explanation.factors.separation && (
                            <div className="bg-slate-900 p-2 rounded border border-slate-800">
                              <span className="text-[11px] text-cyan-300 font-medium block">
                                Separation Proximity
                              </span>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                {event.risk_explanation.factors.separation.description}
                              </p>
                              <div className="mt-1 flex justify-between text-[11px] font-mono text-slate-300">
                                <span>Weight: {event.risk_explanation.factors.separation.weight}</span>
                                <span>
                                  Contrib: +{event.risk_explanation.factors.separation.contribution}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* Relative Velocity */}
                          {event.risk_explanation.factors.relative_velocity && (
                            <div className="bg-slate-900 p-2 rounded border border-slate-800">
                              <span className="text-[11px] text-cyan-300 font-medium block">
                                Relative Velocity
                              </span>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                {event.risk_explanation.factors.relative_velocity.description}
                              </p>
                              <div className="mt-1 flex justify-between text-[11px] font-mono text-slate-300">
                                <span>Weight: {event.risk_explanation.factors.relative_velocity.weight}</span>
                                <span>
                                  Contrib: +{event.risk_explanation.factors.relative_velocity.contribution}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* Urgency */}
                          {event.risk_explanation.factors.time_to_tca && (
                            <div className="bg-slate-900 p-2 rounded border border-slate-800">
                              <span className="text-[11px] text-cyan-300 font-medium block">
                                Encounter Urgency (TCA)
                              </span>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                {event.risk_explanation.factors.time_to_tca.description}
                              </p>
                              <div className="mt-1 flex justify-between text-[11px] font-mono text-slate-300">
                                <span>Weight: {event.risk_explanation.factors.time_to_tca.weight}</span>
                                <span>
                                  Contrib: +{event.risk_explanation.factors.time_to_tca.contribution}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* Anomaly */}
                          <div className="bg-slate-900 p-2 rounded border border-slate-800">
                            <span className="text-[11px] text-cyan-300 font-medium block">
                              Layer 8 Anomaly Context
                            </span>
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              {event.risk_explanation.anomaly_data_available
                                ? `Score: ${event.threat_anomaly_score?.toFixed(3)} (${event.threat_anomaly_severity})`
                                : 'Anomaly detection context unavailable for this candidate.'}
                            </p>
                            <div className="mt-1 flex justify-between text-[11px] font-mono text-slate-300">
                              <span>
                                Weight: {event.risk_explanation.factors.anomaly_score?.weight ?? 0.2}
                              </span>
                              <span>
                                Contrib: +{event.risk_explanation.factors.anomaly_score?.contribution ?? 0}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
