import { useEffect, useState } from 'react'
import { getCatalogStatus } from '../../api/catalog'
import type { CatalogStatusResponse } from '../../types/api'
import LoadingSpinner from '../common/LoadingSpinner'

export default function CatalogFreshnessCard() {
  const [data, setData] = useState<CatalogStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadStatus = () => {
    setLoading(true)
    setError(null)
    getCatalogStatus()
      .then((res) => setData(res))
      .catch((err) => setError(err.message || 'Failed to retrieve catalogue status.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const formatIso = (iso: string | null | undefined) => {
    if (!iso) return 'Not recorded'
    try {
      const dt = new Date(iso)
      return dt.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZoneName: 'short',
      })
    } catch {
      return iso
    }
  }

  const getStatusBadge = () => {
    if (!data) return null
    if (data.refresh_status === 'success') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-600/50">
          Sync Status: Fresh
        </span>
      )
    }
    if (data.refresh_status === 'partial') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-900/60 text-amber-300 border border-amber-600/50">
          Sync Status: Partial
        </span>
      )
    }
    if (data.refresh_status === 'failed') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-900/60 text-rose-300 border border-rose-600/50">
          Sync Status: Failed (Last Known Good Active)
        </span>
      )
    }
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-700 text-slate-300 border border-slate-600">
        Sync Status: Local Snapshot
      </span>
    )
  }

  // Calculate regime percentages for chart
  const regimes = data?.orbit_regimes || { LEO: 15269, MEO: 204, GEO: 563, Other: 11 }
  const totalInRegimes = Object.values(regimes).reduce((a, b) => a + b, 0) || 1
  const leoPct = ((regimes['LEO'] || 0) / totalInRegimes) * 100
  const meoPct = ((regimes['MEO'] || 0) / totalInRegimes) * 100
  const geoPct = ((regimes['GEO'] || 0) / totalInRegimes) * 100
  const otherPct = ((regimes['Other'] || 0) / totalInRegimes) * 100

  return (
    <section className="mb-8" id="catalog-freshness-panel">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest">
          Catalogue & Data Freshness
        </h2>
        {data && getStatusBadge()}
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
        {loading ? (
          <div className="flex items-center gap-3 text-slate-400 text-sm py-4">
            <LoadingSpinner size="sm" />
            <span>Checking catalogue synchronization and orbital epoch freshness…</span>
          </div>
        ) : error ? (
          <div className="flex items-center justify-between text-rose-400 text-sm py-2">
            <span>Catalogue status unavailable: {error}</span>
            <button
              onClick={loadStatus}
              className="text-xs text-cyan-400 hover:text-cyan-300 underline font-medium"
            >
              Retry
            </button>
          </div>
        ) : data ? (
          <div className="space-y-6">
            {/* Metric row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3">
                <div className="text-xs text-slate-400 mb-1">Total Objects</div>
                <div className="text-xl font-bold font-mono text-slate-100">
                  {data.total_objects.toLocaleString()}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  {data.with_orbital_data.toLocaleString()} with orbital elements
                </div>
              </div>

              <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3">
                <div className="text-xs text-slate-400 mb-1">Active Satellites</div>
                <div className="text-xl font-bold font-mono text-cyan-400">
                  {data.active_satellites.toLocaleString()}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">Operational orbital group</div>
              </div>

              <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3">
                <div className="text-xs text-slate-400 mb-1">Oldest Epoch Age</div>
                <div className="text-xl font-bold font-mono text-amber-300">
                  {data.max_epoch_age_days !== null ? `${data.max_epoch_age_days}d` : 'N/A'}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  {data.max_epoch_age_days && data.max_epoch_age_days > 14
                    ? 'Advisory accuracy'
                    : 'Current epoch'}
                </div>
              </div>

              <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3">
                <div className="text-xs text-slate-400 mb-1">Last Sync Check</div>
                <div className="text-sm font-medium text-slate-200 truncate">
                  {data.last_successful_refresh ? formatIso(data.last_successful_refresh) : 'Static File'}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  {data.last_refresh_attempt ? `Attempted: ${formatIso(data.last_refresh_attempt)}` : 'Manual ingest'}
                </div>
              </div>
            </div>

            {/* Orbit Regimes & Altitude Distribution Chart */}
            <div className="bg-slate-900/80 border border-slate-700/70 rounded-lg p-4 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Orbital Altitude & Regime Distribution
                </h3>
                <span className="text-[11px] text-slate-400 font-mono">
                  {data.total_objects.toLocaleString()} Objects In Catalogue
                </span>
              </div>

              {/* Stacked Distribution Bar */}
              <div className="w-full h-4 bg-slate-800 rounded-full overflow-hidden flex border border-slate-700">
                <div
                  className="bg-cyan-500 transition-all duration-500"
                  style={{ width: `${leoPct}%` }}
                  title={`LEO: ${regimes['LEO']?.toLocaleString()} (${leoPct.toFixed(1)}%)`}
                />
                <div
                  className="bg-blue-500 transition-all duration-500"
                  style={{ width: `${meoPct}%` }}
                  title={`MEO: ${regimes['MEO']?.toLocaleString()} (${meoPct.toFixed(1)}%)`}
                />
                <div
                  className="bg-emerald-500 transition-all duration-500"
                  style={{ width: `${geoPct}%` }}
                  title={`GEO: ${regimes['GEO']?.toLocaleString()} (${geoPct.toFixed(1)}%)`}
                />
                <div
                  className="bg-purple-500 transition-all duration-500"
                  style={{ width: `${otherPct}%` }}
                  title={`Other/HEO: ${regimes['Other']?.toLocaleString()} (${otherPct.toFixed(1)}%)`}
                />
              </div>

              {/* Regime Legend Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-xs">
                <div className="bg-slate-800/80 rounded p-2 border border-slate-700/60">
                  <div className="flex items-center gap-1.5 text-cyan-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-cyan-400" />
                    <span>LEO (&lt;2,000 km)</span>
                  </div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                    {regimes['LEO']?.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">{leoPct.toFixed(1)}% of catalogue</span>
                </div>

                <div className="bg-slate-800/80 rounded p-2 border border-slate-700/60">
                  <div className="flex items-center gap-1.5 text-blue-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-blue-400" />
                    <span>MEO (2,000–35k km)</span>
                  </div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                    {regimes['MEO']?.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">{meoPct.toFixed(1)}% of catalogue</span>
                </div>

                <div className="bg-slate-800/80 rounded p-2 border border-slate-700/60">
                  <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    <span>GEO (~35,786 km)</span>
                  </div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                    {regimes['GEO']?.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">{geoPct.toFixed(1)}% of catalogue</span>
                </div>

                <div className="bg-slate-800/80 rounded p-2 border border-slate-700/60">
                  <div className="flex items-center gap-1.5 text-purple-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-purple-400" />
                    <span>HEO / Deep Space</span>
                  </div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                    {regimes['Other']?.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">{otherPct.toFixed(1)}% of catalogue</span>
                </div>
              </div>
            </div>

            {/* Object Classification Provenance & Coverage Box */}
            <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3.5 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-300">Catalogue Classification Coverage</span>
                <span className="text-[10px] text-slate-400">SATCAT Metadata Notice</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-slate-300 text-xs">
                <div className="bg-slate-800/60 p-2 rounded border border-slate-700/50">
                  <span className="text-[10px] text-slate-400 block">Active Satellites</span>
                  <span className="font-mono font-bold text-cyan-400">{data.active_satellites.toLocaleString()}</span>
                  <span className="text-[10px] text-emerald-400 block mt-0.5">✓ Loaded</span>
                </div>
                <div className="bg-slate-800/60 p-2 rounded border border-slate-700/50">
                  <span className="text-[10px] text-slate-400 block">Inactive Payloads</span>
                  <span className="font-mono font-bold text-slate-400">0</span>
                  <span className="text-[10px] text-slate-500 block mt-0.5">Requires SATCAT</span>
                </div>
                <div className="bg-slate-800/60 p-2 rounded border border-slate-700/50">
                  <span className="text-[10px] text-slate-400 block">Rocket Bodies</span>
                  <span className="font-mono font-bold text-slate-400">0</span>
                  <span className="text-[10px] text-slate-500 block mt-0.5">Requires SATCAT</span>
                </div>
                <div className="bg-slate-800/60 p-2 rounded border border-slate-700/50">
                  <span className="text-[10px] text-slate-400 block">Debris Fragments</span>
                  <span className="font-mono font-bold text-slate-400">0</span>
                  <span className="text-[10px] text-slate-500 block mt-0.5">Requires Debris GP</span>
                </div>
              </div>
            </div>

            {/* Warnings list */}
            {data.warnings && data.warnings.length > 0 && (
              <div className="bg-amber-950/30 border border-amber-800/50 rounded-md p-3 space-y-1">
                <div className="text-xs font-semibold text-amber-400 flex items-center gap-1.5">
                  <svg className="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Data Freshness & Epoch Notice
                </div>
                {data.warnings.map((w, idx) => (
                  <p key={idx} className="text-xs text-amber-300/90 pl-5">
                    • {w}
                  </p>
                ))}
              </div>
            )}

            {/* Footer provenance note */}
            <div className="text-[11px] text-slate-500 pt-1 flex items-center justify-between border-t border-slate-700/50">
              <span>
                Source: CelesTrak GP Dataset · Download time does NOT equal orbital generation epoch.
              </span>
              <button
                onClick={loadStatus}
                className="text-cyan-400 hover:text-cyan-300 text-xs font-medium inline-flex items-center gap-1 transition-colors"
              >
                ↻ Refresh Status
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
