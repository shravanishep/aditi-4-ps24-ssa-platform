import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import apiFetch from '../api/client'
import { listSatellites } from '../api/satellites'
import type { SatelliteBasicInfo } from '../types/api'
import StatusBadge from '../components/common/StatusBadge'
import LoadingSpinner from '../components/common/LoadingSpinner'
import ThreatPrioritizationPanel from '../components/threats/ThreatPrioritizationPanel'
import CatalogFreshnessCard from '../components/catalog/CatalogFreshnessCard'
import MLAnomalyPanel from '../components/ml/MLAnomalyPanel'

type HealthStatus = 'loading' | 'ok' | 'error'

export default function DashboardPage() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus>('loading')
  const [satellites, setSatellites] = useState<SatelliteBasicInfo[] | null>(null)
  const [satellitesLoading, setSatellitesLoading] = useState(true)

  useEffect(() => {
    apiFetch<{ status: string }>('/health')
      .then(() => setHealthStatus('ok'))
      .catch(() => setHealthStatus('error'))
  }, [])

  useEffect(() => {
    listSatellites(5)
      .then(data => setSatellites(data))
      .catch(() => setSatellites(null))
      .finally(() => setSatellitesLoading(false))
  }, [])

  return (
    <div className="p-8 max-w-5xl space-y-8">
      {/* Platform Title */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100 tracking-tight">
          ADITI 4.0 SSA Platform
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Space Situational Awareness (SSA) · Orbital Surveillance, Conjunction Screening & Maneuver Analysis Platform
        </p>
      </div>

      {/* System Status Banner */}
      <section>
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
          1. System Status & Health
        </h2>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <StatusBadge status={healthStatus} />
            <span className="text-slate-300 text-sm font-medium">
              {healthStatus === 'loading' && 'Probing backend API service…'}
              {healthStatus === 'ok' && 'Backend API is online and responding normally on port 8000.'}
              {healthStatus === 'error' &&
                'Backend API is unavailable. Ensure the FastAPI server is running on port 8000.'}
            </span>
          </div>
          <span className="text-xs font-mono text-slate-500 hidden sm:inline">
            FastAPI v0.5.0
          </span>
        </div>
      </section>

      {/* Catalogue Freshness & Sync Status */}
      <CatalogFreshnessCard />

      {/* Threat Prioritization & Screening */}
      <ThreatPrioritizationPanel />

      {/* Layer 8 ML Anomaly Detection & Regime Telemetry */}
      <MLAnomalyPanel />

      {/* Sample Objects from Ingested Dataset */}
      <section>
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
          Verified Catalogue Samples
        </h2>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          {satellitesLoading ? (
            <div className="flex items-center gap-3 text-slate-400 text-sm">
              <LoadingSpinner size="sm" />
              <span>Loading satellite sample from catalogue…</span>
            </div>
          ) : satellites && satellites.length > 0 ? (
            <div>
              <p className="text-xs text-slate-400 mb-3">
                Showing sample operational payloads from CelesTrak GP dataset. Use Satellite Explorer for full lookups.
              </p>
              <div className="space-y-2">
                {satellites.map(sat => (
                  <div key={sat.norad_cat_id} className="flex items-center justify-between p-2 rounded bg-slate-900/40 border border-slate-700/50 text-xs">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sky-400 font-semibold w-14">
                        #{sat.norad_cat_id}
                      </span>
                      <span className="text-slate-200 font-medium">{sat.object_name}</span>
                    </div>
                    <Link
                      to={`/satellites?norad=${sat.norad_cat_id}`}
                      className="text-sky-400 hover:text-sky-300 text-[11px]"
                    >
                      Inspect Orbit →
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-slate-500 text-sm">
              Unable to load satellite sample — check backend connection.
            </p>
          )}
        </div>
      </section>

      {/* Core Platform Analysis Modules */}
      <section>
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
          Analysis & Operational Modules
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/satellites"
            className="block bg-slate-800 hover:bg-slate-700/80 border border-slate-700 hover:border-slate-600 rounded-lg p-5 transition-colors group"
          >
            <p className="text-sm font-bold text-slate-100 group-hover:text-sky-300 mb-1">
              Satellite Explorer
            </p>
            <p className="text-slate-400 text-xs leading-relaxed">
              Query Keplerian orbital parameters, perigee/apogee altitudes, inclination, SGP4 drag parameters, and propagate future Cartesian states.
            </p>
          </Link>
          <Link
            to="/conjunction"
            className="block bg-slate-800 hover:bg-slate-700/80 border border-slate-700 hover:border-slate-600 rounded-lg p-5 transition-colors group"
          >
            <p className="text-sm font-bold text-slate-100 group-hover:text-sky-300 mb-1">
              Conjunction Analysis & CAM
            </p>
            <p className="text-slate-400 text-xs leading-relaxed">
              Bisection search for Time of Closest Approach (TCA) and miss distance between satellite pairs. Simulate impulsive CAM burns with RK4 numerical propagation.
            </p>
          </Link>
          <Link
            to="/pc-analysis"
            className="block bg-slate-800 hover:bg-slate-700/80 border border-slate-700 hover:border-slate-600 rounded-lg p-5 transition-colors group"
          >
            <p className="text-sm font-bold text-slate-100 group-hover:text-sky-300 mb-1">
              Collision Probability & CDM
            </p>
            <p className="text-slate-400 text-xs leading-relaxed">
              Ingest CCSDS Conjunction Data Messages (CDM), validate symmetric positive semi-definite (PSD) covariance, and calculate Foster 2-D encounter-plane Pc.
            </p>
          </Link>
        </div>
      </section>
    </div>
  )
}
