import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import apiFetch from '../api/client'
import { listSatellites } from '../api/satellites'
import type { SatelliteBasicInfo } from '../types/api'
import StatusBadge from '../components/common/StatusBadge'
import LoadingSpinner from '../components/common/LoadingSpinner'

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
    <div className="p-8 max-w-4xl">
      {/* Title */}
      <h1 className="text-2xl font-bold text-slate-100 mb-1">
        ADITI 4.0 SSA Platform
      </h1>
      <p className="text-slate-400 text-sm mb-8">
        AI-assisted Space Situational Awareness · Orbital Analysis Prototype
      </p>

      {/* System Status */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3">
          System Status
        </h2>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 flex items-center gap-3">
          <StatusBadge status={healthStatus} />
          <span className="text-slate-300 text-sm">
            {healthStatus === 'loading' && 'Checking backend…'}
            {healthStatus === 'ok' && 'Backend API is responding normally.'}
            {healthStatus === 'error' &&
              'Backend API is unavailable. Ensure the FastAPI server is running on port 8000.'}
          </span>
        </div>
      </section>

      {/* Satellite sample */}
      <section className="mb-8">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3">
          Sample Objects from GP Dataset
        </h2>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          {satellitesLoading ? (
            <div className="flex items-center gap-3 text-slate-400 text-sm">
              <LoadingSpinner size="sm" />
              <span>Loading satellite sample…</span>
            </div>
          ) : satellites && satellites.length > 0 ? (
            <div>
              <p className="text-xs text-slate-500 mb-3">
                Showing {satellites.length} sample objects. Use Satellite Explorer for full lookups.
              </p>
              <div className="space-y-1.5">
                {satellites.map(sat => (
                  <div key={sat.norad_cat_id} className="flex items-center gap-4 text-sm">
                    <span className="font-mono text-cyan-400 w-10 shrink-0">
                      {sat.norad_cat_id}
                    </span>
                    <span className="text-slate-300">{sat.object_name}</span>
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

      {/* Navigation cards */}
      <section>
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3">
          Analysis Tools
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Link
            to="/satellites"
            className="block bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-cyan-700 rounded-lg p-5 transition-colors group"
          >
            <p className="text-base font-semibold text-slate-100 group-hover:text-cyan-300 mb-1">
              Satellite Explorer
            </p>
            <p className="text-slate-400 text-sm">
              Search by NORAD ID. View GP orbital parameters and propagate position and velocity to any UTC time.
            </p>
          </Link>
          <Link
            to="/conjunction"
            className="block bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-cyan-700 rounded-lg p-5 transition-colors group"
          >
            <p className="text-base font-semibold text-slate-100 group-hover:text-cyan-300 mb-1">
              Conjunction Analysis
            </p>
            <p className="text-slate-400 text-sm">
              Find the approximate Time of Closest Approach between two objects using SGP4 propagation.
            </p>
          </Link>
        </div>
      </section>
    </div>
  )
}
