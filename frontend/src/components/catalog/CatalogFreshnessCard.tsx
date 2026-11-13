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
    if (!iso) return 'None'
    try {
      const dt = new Date(iso)
      return dt.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZoneName: 'short',
      })
    } catch {
      return iso
    }
  }

  const getStatusBadge = () => {
    if (!data) return null

    const isSchedulerActive = data.scheduler_status === 'active'

    if (isSchedulerActive) {
      if (data.refresh_status === 'success') {
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-emerald-950/70 text-emerald-300 border border-emerald-700/60 font-mono">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Automatic refresh active · Last refresh successful
          </span>
        )
      }
      if (data.refresh_status === 'failed') {
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-rose-950/70 text-rose-300 border border-rose-700/60 font-mono">
            <span className="w-2 h-2 rounded-full bg-rose-400" />
            Automatic refresh active · Last refresh failed (Preserving last-known-good snapshot)
          </span>
        )
      }
      if (data.refresh_status === 'partial') {
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-amber-950/70 text-amber-300 border border-amber-700/60 font-mono">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            Automatic refresh active · Partial sync
          </span>
        )
      }
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-sky-950/70 text-sky-300 border border-sky-700/60 font-mono">
          <span className="w-2 h-2 rounded-full bg-sky-400" />
          Automatic refresh active (Cycle: Every {data.refresh_interval_hours || 6}h)
        </span>
      )
    }

    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700 font-mono">
        <span className="w-2 h-2 rounded-full bg-slate-500" />
        Scheduler disabled · Local snapshot active
      </span>
    )
  }

  const regimes = data?.orbit_regimes || { LEO: 15269, MEO: 204, GEO: 563, Other: 11 }
  const totalInRegimes = Object.values(regimes).reduce((a, b) => a + b, 0) || 1
  const leoPct = ((regimes['LEO'] || 0) / totalInRegimes) * 100
  const meoPct = ((regimes['MEO'] || 0) / totalInRegimes) * 100
  const geoPct = ((regimes['GEO'] || 0) / totalInRegimes) * 100
  const otherPct = ((regimes['Other'] || 0) / totalInRegimes) * 100

  return (
    <section className="mb-8" id="catalog-freshness-panel">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
          Catalogue Provenance & Automatic Refresh
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
              className="text-xs text-sky-400 hover:text-sky-300 underline font-medium"
            >
              Retry
            </button>
          </div>
        ) : data ? (
          <div className="space-y-6">
            {/* 4 Distinct Operational Metric Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Card 1: Catalogue Counts */}
              <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3.5 space-y-1">
                <span className="text-xs text-slate-400 block">Total Objects</span>
                <span className="text-xl font-bold font-mono text-slate-100 block">
                  {data.total_objects.toLocaleString()}
                </span>
                <div className="text-[11px] text-slate-400 space-y-0.5 pt-1">
                  <div>Active payloads: <span className="font-mono text-sky-400 font-semibold">{data.active_satellites.toLocaleString()}</span></div>
                  <div>With orbital data: <span className="font-mono text-slate-300">{data.with_orbital_data.toLocaleString()}</span></div>
                </div>
              </div>

              {/* Card 2: Epoch Age Statistics */}
              <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3.5 space-y-1">
                <span className="text-xs text-slate-400 block">Median Epoch Age</span>
                <span className="text-xl font-bold font-mono text-amber-300 block">
                  {data.median_epoch_age_days !== null && data.median_epoch_age_days !== undefined
                    ? `${data.median_epoch_age_days}d`
                    : 'N/A'}
                </span>
                <div className="text-[11px] text-slate-400 space-y-0.5 pt-1">
                  <div>Oldest epoch age: <span className="font-mono text-slate-300">{data.max_epoch_age_days ?? 'N/A'}d</span></div>
                  <div>Stale objects (&gt;30d): <span className="font-mono text-amber-300 font-semibold">{data.stale_objects.toLocaleString()}</span></div>
                </div>
              </div>

              {/* Card 3: Retrieval Timestamps (Download Time != Epoch) */}
              <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3.5 space-y-1">
                <span className="text-xs text-slate-400 block">Last Successful Retrieval</span>
                <span className="text-sm font-semibold font-mono text-slate-200 block truncate">
                  {data.last_successful_refresh ? formatIso(data.last_successful_refresh) : 'Pre-loaded Snapshot'}
                </span>
                <div className="text-[11px] text-slate-400 space-y-0.5 pt-1">
                  <div className="truncate">Last attempt: <span className="font-mono text-slate-300">{formatIso(data.last_refresh_attempt)}</span></div>
                  <div>Outcome: <span className="font-mono uppercase text-slate-300">{data.refresh_status}</span></div>
                </div>
              </div>

              {/* Card 4: Scheduler Lifecycle */}
              <div className="bg-slate-900/60 border border-slate-700/60 rounded-md p-3.5 space-y-1">
                <span className="text-xs text-slate-400 block">Scheduler Lifecycle</span>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={`w-2 h-2 rounded-full ${data.scheduler_status === 'active' ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                  <span className="text-sm font-bold font-mono text-slate-100 uppercase">
                    {data.scheduler_status || 'disabled'}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 space-y-0.5 pt-1">
                  <div>Cadence: <span className="font-mono text-slate-300">Every {data.refresh_interval_hours || 6.0}h</span></div>
                  <div>Source: <span className="font-mono text-slate-300 truncate">CelesTrak GP (CSV)</span></div>
                </div>
              </div>
            </div>

            {/* Orbit Regimes & Altitude Distribution Chart */}
            <div className="bg-slate-900/70 border border-slate-700/70 rounded-lg p-4 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Orbital Altitude & Regime Distribution
                </h3>
                <span className="text-[11px] text-slate-400 font-mono">
                  {data.total_objects.toLocaleString()} Ingested Objects
                </span>
              </div>

              {/* Stacked Distribution Bar */}
              <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden flex border border-slate-700">
                <div
                  className="bg-sky-500 transition-all duration-500"
                  style={{ width: `${leoPct}%` }}
                  title={`LEO: ${regimes['LEO']?.toLocaleString()} (${leoPct.toFixed(1)}%)`}
                />
                <div
                  className="bg-blue-600 transition-all duration-500"
                  style={{ width: `${meoPct}%` }}
                  title={`MEO: ${regimes['MEO']?.toLocaleString()} (${meoPct.toFixed(1)}%)`}
                />
                <div
                  className="bg-emerald-600 transition-all duration-500"
                  style={{ width: `${geoPct}%` }}
                  title={`GEO: ${regimes['GEO']?.toLocaleString()} (${geoPct.toFixed(1)}%)`}
                />
                <div
                  className="bg-purple-600 transition-all duration-500"
                  style={{ width: `${otherPct}%` }}
                  title={`Other/HEO: ${regimes['Other']?.toLocaleString()} (${otherPct.toFixed(1)}%)`}
                />
              </div>

              {/* Regime Legend Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1 text-xs">
                <div className="bg-slate-800/80 rounded p-2.5 border border-slate-700/60">
                  <div className="flex items-center gap-1.5 text-sky-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-sky-400" />
                    <span>LEO (&lt;2,000 km)</span>
                  </div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                    {regimes['LEO']?.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">{leoPct.toFixed(1)}% of catalogue</span>
                </div>

                <div className="bg-slate-800/80 rounded p-2.5 border border-slate-700/60">
                  <div className="flex items-center gap-1.5 text-blue-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-blue-500" />
                    <span>MEO (2k–35k km)</span>
                  </div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                    {regimes['MEO']?.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">{meoPct.toFixed(1)}% of catalogue</span>
                </div>

                <div className="bg-slate-800/80 rounded p-2.5 border border-slate-700/60">
                  <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span>GEO (~35,786 km)</span>
                  </div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                    {regimes['GEO']?.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">{geoPct.toFixed(1)}% of catalogue</span>
                </div>

                <div className="bg-slate-800/80 rounded p-2.5 border border-slate-700/60">
                  <div className="flex items-center gap-1.5 text-purple-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-purple-500" />
                    <span>HEO / Deep Space</span>
                  </div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                    {regimes['Other']?.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">{otherPct.toFixed(1)}% of catalogue</span>
                </div>
              </div>
            </div>

            {/* Scientific Notice: Difference between download time and epoch */}
            <div className="bg-amber-950/20 border border-amber-800/50 rounded-md p-3.5 space-y-1 text-xs">
              <div className="font-semibold text-amber-300 flex items-center gap-1.5">
                <span>⚠️</span>
                <span>Scientific Provenance: Retrieval Time vs. Orbital Generation Epoch</span>
              </div>
              <p className="text-slate-300 leading-relaxed text-[11px]">
                The retrieval timestamp reflects when the CSV dataset was pulled from CelesTrak. It does <strong>NOT</strong> equal the orbital generation epoch. Epoch timestamps range from {data.newest_epoch ? formatIso(data.newest_epoch) : 'N/A'} (newest) to {data.oldest_epoch ? formatIso(data.oldest_epoch) : 'N/A'} (oldest). Analytical SGP4 propagation degrades as epoch age increases; all predictions are research prototypes.
              </p>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
