import { useState, useEffect, useCallback } from 'react'
import { getEvents, getEventStats } from '../api/events'
import { ApiError } from '../api/client'
import type { EventResponse } from '../types/api'
import LoadingSpinner from '../components/common/LoadingSpinner'
import ErrorMessage from '../components/common/ErrorMessage'

export default function EventTimelinePage() {
  const [events, setEvents] = useState<EventResponse[]>([])
  const [stats, setStats] = useState<{
    total: number
    by_type: Record<string, number>
    by_classification: Record<string, number>
  } | null>(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [noradFilter, setNoradFilter] = useState<string>('')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [classFilter, setClassFilter] = useState<string>('')
  const [selectedEvent, setSelectedEvent] = useState<EventResponse | null>(null)

  const fetchEvents = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getEvents({
        norad_id: noradFilter ? parseInt(noradFilter, 10) : undefined,
        event_type: typeFilter || undefined,
        classification: classFilter || undefined,
        limit: 100,
      })
      setEvents(data.events)

      const statsData = await getEventStats()
      setStats(statsData)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Failed to load event timeline (${err.status}): ${err.message}`)
      } else {
        setError('Failed to load event timeline from backend database. Verify server connection.')
      }
    } finally {
      setLoading(false)
    }
  }, [noradFilter, typeFilter, classFilter])

  useEffect(() => {
    fetchEvents()
  }, [fetchEvents])

  const getClassificationBadge = (cls?: string | null) => {
    switch (cls) {
      case 'ORBIT_RAISE':
        return 'bg-amber-950/70 text-amber-300 border-amber-700/60'
      case 'ORBIT_DECAY':
        return 'bg-rose-950/70 text-rose-300 border-rose-700/60'
      case 'STATION_KEEPING':
        return 'bg-emerald-950/70 text-emerald-300 border-emerald-700/60'
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700'
    }
  }

  const getTypeBadge = (type: string) => {
    switch (type) {
      case 'THREAT':
        return 'bg-rose-950/70 text-rose-300 border-rose-800'
      case 'CONJUNCTION':
        return 'bg-amber-950/70 text-amber-300 border-amber-800'
      case 'ANOMALY':
        return 'bg-purple-950/70 text-purple-300 border-purple-800'
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700'
    }
  }

  const hasActiveFilters = Boolean(noradFilter || typeFilter || classFilter)

  const handleClearFilters = () => {
    setNoradFilter('')
    setTypeFilter('')
    setClassFilter('')
  }

  return (
    <div className="p-8 max-w-7xl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <span className="text-sky-400 font-mono text-lg">📜</span> Event Intelligence & Persistent Timeline
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Historical audit log of orbital anomalies, close-approach threats, and rule-based maneuver classifications.
          </p>
        </div>
        <button
          onClick={fetchEvents}
          disabled={loading}
          className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 border border-slate-700 px-3.5 py-1.5 rounded text-xs transition-colors self-start sm:self-auto"
        >
          {loading ? 'Refreshing…' : '↻ Refresh Log'}
        </button>
      </div>

      {/* Advisory Banner */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-lg p-3.5 mb-6 flex items-start gap-3 text-xs text-slate-300">
        <span className="text-sky-400 font-bold text-sm leading-none mt-0.5">ℹ</span>
        <div className="space-y-1">
          <span className="font-semibold text-slate-200">Rule-Based Maneuver Classification: </span>
          <span className="text-slate-400 leading-relaxed">
            Classifications (STATION_KEEPING, ORBIT_RAISE, ORBIT_DECAY, UNKNOWN) are transparent, deterministic heuristics based on rate-of-change thresholds of orbital elements over time. Events are persistently stored in an append-only SQLite database.
          </span>
        </div>
      </div>

      {/* Summary Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3.5">
            <span className="text-slate-400 text-xs block">Total Logged Events</span>
            <span className="text-xl font-bold font-mono text-slate-100 mt-1 block">
              {stats.total.toLocaleString()}
            </span>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3.5">
            <span className="text-slate-400 text-xs block">Conjunction Events</span>
            <span className="text-xl font-bold font-mono text-amber-300 mt-1 block">
              {(stats.by_type?.CONJUNCTION || 0).toLocaleString()}
            </span>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3.5">
            <span className="text-slate-400 text-xs block">Anomalies Detected</span>
            <span className="text-xl font-bold font-mono text-purple-300 mt-1 block">
              {(stats.by_type?.ANOMALY || 0).toLocaleString()}
            </span>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3.5">
            <span className="text-slate-400 text-xs block">Maneuvers Classified</span>
            <span className="text-xl font-bold font-mono text-emerald-400 mt-1 block">
              {(
                (stats.by_classification?.STATION_KEEPING || 0) +
                (stats.by_classification?.ORBIT_RAISE || 0) +
                (stats.by_classification?.ORBIT_DECAY || 0)
              ).toLocaleString()}
            </span>
          </div>
        </div>
      )}

      {/* Filters Bar */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">NORAD Catalog ID</label>
            <input
              type="number"
              placeholder="e.g. 25544"
              value={noradFilter}
              onChange={(e) => setNoradFilter(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-sky-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">Event Type</label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500"
            >
              <option value="">All Event Types</option>
              <option value="CONJUNCTION">CONJUNCTION</option>
              <option value="ANOMALY">ANOMALY</option>
              <option value="THREAT">THREAT</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">Classification</label>
            <select
              value={classFilter}
              onChange={(e) => setClassFilter(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500"
            >
              <option value="">All Classifications</option>
              <option value="STATION_KEEPING">STATION_KEEPING</option>
              <option value="ORBIT_RAISE">ORBIT_RAISE</option>
              <option value="ORBIT_DECAY">ORBIT_DECAY</option>
              <option value="UNKNOWN">UNKNOWN</option>
            </select>
          </div>

          <div>
            {hasActiveFilters && (
              <button
                type="button"
                onClick={handleClearFilters}
                className="w-full bg-slate-700 hover:bg-slate-600 text-slate-200 px-3 py-1.5 rounded text-xs transition-colors"
              >
                Clear Filters
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Main Content: Loading, Error, or Table/Empty State */}
      {loading ? (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-12 text-center text-slate-400">
          <LoadingSpinner size="md" />
          <p className="mt-2 text-xs">Loading event timeline from SQLite store…</p>
        </div>
      ) : error ? (
        /* If there is an error, show ONLY the Error message with retry — NEVER show 'No Events Found' simultaneously */
        <div className="space-y-4">
          <ErrorMessage message={error} />
          <div className="text-center">
            <button
              onClick={fetchEvents}
              className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 px-4 py-2 rounded text-xs transition-colors"
            >
              Retry Loading Events
            </button>
          </div>
        </div>
      ) : events.length === 0 ? (
        /* Clean, informative empty state */
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-12 text-center text-slate-400 text-xs">
          <p className="text-sm font-semibold text-slate-200 mb-1">
            {hasActiveFilters ? 'No Matching Events Found' : 'No Events in Timeline'}
          </p>
          <p className="max-w-md mx-auto text-slate-400">
            {hasActiveFilters
              ? 'No historical events match the current filter criteria. Try clearing or relaxing the filters.'
              : 'The persistent SQLite event database is currently empty. Run a Conjunction Analysis and click "Log Maneuver to Timeline", or trigger Threat Screening to record events.'}
          </p>
          {hasActiveFilters && (
            <button
              onClick={handleClearFilters}
              className="mt-4 bg-slate-700 hover:bg-slate-600 text-slate-200 px-3.5 py-1.5 rounded text-xs transition-colors"
            >
              Clear Active Filters
            </button>
          )}
        </div>
      ) : (
        /* Events Table */
        <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-700">
                <tr>
                  <th className="py-2.5 px-4 font-medium">Detection Time (UTC)</th>
                  <th className="py-2.5 px-4 font-medium">Object</th>
                  <th className="py-2.5 px-4 font-medium">Type</th>
                  <th className="py-2.5 px-4 font-medium">Classification</th>
                  <th className="py-2.5 px-4 font-medium">Miss Dist / Score</th>
                  <th className="py-2.5 px-4 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/60 text-slate-300">
                {events.map((ev) => (
                  <tr
                    key={ev.id}
                    onClick={() => setSelectedEvent(ev)}
                    className="hover:bg-slate-700/40 cursor-pointer transition-colors"
                  >
                    <td className="py-2.5 px-4 font-mono text-slate-400">
                      {new Date(ev.detected_at).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-4">
                      <span className="font-semibold text-slate-100">{ev.object_name || `Object #${ev.norad_id}`}</span>
                      <span className="text-slate-500 font-mono block text-[10px]">#{ev.norad_id}</span>
                    </td>
                    <td className="py-2.5 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${getTypeBadge(ev.event_type)}`}>
                        {ev.event_type}
                      </span>
                    </td>
                    <td className="py-2.5 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-medium border ${getClassificationBadge(ev.classification)}`}>
                        {ev.classification || 'UNKNOWN'}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 font-mono">
                      {ev.miss_distance_km !== null && ev.miss_distance_km !== undefined ? (
                        <span className="text-amber-400 font-semibold">{ev.miss_distance_km.toFixed(2)} km</span>
                      ) : ev.threat_score !== null && ev.threat_score !== undefined ? (
                        <span className="text-sky-400">Score: {ev.threat_score.toFixed(3)}</span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-sky-400 hover:text-sky-300 font-medium">
                      Inspect →
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Selected Event Details Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 max-w-lg w-full space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-700 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-100">
                  {selectedEvent.object_name || `Object #${selectedEvent.norad_id}`}
                </h3>
                <span className="text-[11px] text-slate-400 font-mono">
                  Event ID: {selectedEvent.id} · NORAD: #{selectedEvent.norad_id}
                </span>
              </div>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-slate-400 hover:text-slate-200 text-sm font-mono px-2 py-1 rounded hover:bg-slate-800"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="bg-slate-800/60 p-2.5 rounded border border-slate-700/60">
                <span className="text-slate-400 block text-[10px]">Event Type</span>
                <span className="font-semibold text-slate-200">{selectedEvent.event_type}</span>
              </div>
              <div className="bg-slate-800/60 p-2.5 rounded border border-slate-700/60">
                <span className="text-slate-400 block text-[10px]">Classification</span>
                <span className="font-semibold text-slate-200">{selectedEvent.classification || 'UNKNOWN'}</span>
              </div>
              <div className="bg-slate-800/60 p-2.5 rounded border border-slate-700/60">
                <span className="text-slate-400 block text-[10px]">Detection Time (UTC)</span>
                <span className="font-mono text-slate-200 text-[11px]">{selectedEvent.detected_at}</span>
              </div>
              <div className="bg-slate-800/60 p-2.5 rounded border border-slate-700/60">
                <span className="text-slate-400 block text-[10px]">Data Source</span>
                <span className="text-slate-300">{selectedEvent.data_source}</span>
              </div>
            </div>

            {selectedEvent.classification_explanation && (
              <div className="bg-slate-800/40 border border-slate-700/60 rounded p-3 text-xs">
                <span className="text-slate-400 block text-[10px] mb-1">Classification Explanation</span>
                <p className="text-slate-300 leading-relaxed">{selectedEvent.classification_explanation}</p>
              </div>
            )}

            {(selectedEvent.miss_distance_km !== null || selectedEvent.tca) && (
              <div className="bg-slate-800/40 border border-slate-700/60 rounded p-3 text-xs space-y-1">
                <span className="text-slate-400 block text-[10px]">Close-Approach Parameters</span>
                {selectedEvent.tca && (
                  <div className="text-slate-300">TCA: <span className="font-mono">{selectedEvent.tca}</span></div>
                )}
                {selectedEvent.miss_distance_km !== null && selectedEvent.miss_distance_km !== undefined && (
                  <div className="text-slate-300">Miss Distance: <span className="font-mono font-bold text-amber-300">{selectedEvent.miss_distance_km.toFixed(3)} km</span></div>
                )}
                {selectedEvent.rel_speed_km_s !== null && selectedEvent.rel_speed_km_s !== undefined && (
                  <div className="text-slate-300">Relative Velocity: <span className="font-mono">{selectedEvent.rel_speed_km_s.toFixed(3)} km/s</span></div>
                )}
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedEvent(null)}
                className="bg-slate-700 hover:bg-slate-600 text-slate-200 px-4 py-1.5 rounded text-xs transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
