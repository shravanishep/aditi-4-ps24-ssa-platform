import React, { useCallback, useState } from 'react'
import { getSatellite, getOrbit } from '../api/satellites'
import { getTrajectory } from '../api/trajectory'
import { ApiError } from '../api/client'
import type {
  SatelliteGPInfo,
  PropagatedOrbitStateResponse,
  TrajectoryResponse,
} from '../types/api'
import CesiumGlobe from '../components/globe/CesiumGlobe'
import SatelliteInfoPanel from '../components/globe/SatelliteInfoPanel'
import LoadingSpinner from '../components/common/LoadingSpinner'
import ErrorMessage from '../components/common/ErrorMessage'

const QUICK_SATELLITES = [
  { id: 900, name: 'CALSPHERE 1' },
  { id: 25544, name: 'ISS (ZARYA)' },
  { id: 20580, name: 'HUBBLE (HST)' },
]

export default function GlobePage() {
  const [noradInput, setNoradInput] = useState('900')
  const [timestampInput, setTimestampInput] = useState(() =>
    new Date().toISOString(),
  )

  const [satelliteGP, setSatelliteGP] = useState<SatelliteGPInfo | null>(null)
  const [orbitState, setOrbitState] = useState<PropagatedOrbitStateResponse | null>(null)
  const [trajectory, setTrajectory] = useState<TrajectoryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [flyToFn, setFlyToFn] = useState<(() => void) | null>(null)

  const handleFlyToReady = useCallback((fn: () => void) => {
    setFlyToFn(() => fn)
  }, [])

  async function handleSearch(targetNorad?: number) {
    const noradId = targetNorad !== undefined ? targetNorad : parseInt(noradInput, 10)
    if (isNaN(noradId) || noradId <= 0) {
      setError('Please enter a valid positive NORAD catalog ID.')
      return
    }

    setLoading(true)
    setError(null)

    try {
      // 1. Fetch satellite GP metadata
      const gp = await getSatellite(noradId)
      setSatelliteGP(gp)

      // Ensure timestamp has 'Z' if not offset-aware
      let utcIso = timestampInput.trim()
      if (!utcIso.endsWith('Z') && !utcIso.includes('+') && !utcIso.includes('-')) {
        utcIso += 'Z'
      }

      // 2. Fetch single propagated state at target timestamp
      const orbit = await getOrbit(noradId, utcIso)
      setOrbitState(orbit)

      // 3. Compute ±45 min trajectory window (90 minutes total, 60s step)
      const targetDate = new Date(utcIso)
      const startDate = new Date(targetDate.getTime() - 45 * 60 * 1000)
      const endDate = new Date(targetDate.getTime() + 45 * 60 * 1000)

      const traj = await getTrajectory(
        noradId,
        startDate.toISOString(),
        endDate.toISOString(),
        60.0,
      )
      setTrajectory(traj)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'An unexpected error occurred while loading satellite orbit data.',
      )
    } finally {
      setLoading(false)
    }
  }

  function handleQuickSelect(id: number) {
    setNoradInput(id.toString())
    handleSearch(id)
  }

  function handleSetNow() {
    setTimestampInput(new Date().toISOString())
  }

  return (
    <div
      className="flex flex-col lg:flex-row bg-slate-950 text-slate-100 overflow-hidden"
      style={{ height: '100vh' }}
    >
      {/* Left Control & Info Sidebar */}
      <div className="w-full lg:w-96 shrink-0 bg-slate-900 border-r border-slate-800 p-5 flex flex-col gap-4 overflow-y-auto" style={{ maxHeight: '100vh' }}>
        <div>
          <h1 className="text-lg font-bold text-slate-100">3D Orbital Visualization</h1>
          <p className="text-xs text-slate-400 mt-1">
            Display SGP4 orbital propagation and trajectory on a 3D Earth globe using CesiumJS.
          </p>
        </div>

        {/* Search Controls */}
        <div className="bg-slate-800/60 rounded-lg p-3.5 border border-slate-700/60 flex flex-col gap-3">
          <div>
            <label className="block text-[11px] font-medium text-slate-300 mb-1">
              NORAD Catalog ID
            </label>
            <input
              type="number"
              min="1"
              value={noradInput}
              onChange={(e) => setNoradInput(e.target.value)}
              placeholder="e.g. 900 or 25544"
              className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-sm text-slate-100 focus:outline-none focus:border-cyan-500 font-mono"
            />
          </div>

          {/* Quick select presets */}
          <div>
            <span className="text-[10px] text-slate-400 block mb-1">Quick Select:</span>
            <div className="flex flex-wrap gap-1.5">
              {QUICK_SATELLITES.map((sat) => (
                <button
                  key={sat.id}
                  type="button"
                  onClick={() => handleQuickSelect(sat.id)}
                  className="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-[10px] text-cyan-300 transition-colors"
                >
                  {sat.name}
                </button>
              ))}
            </div>
          </div>

          {/* Timestamp Picker */}
          <div>
            <div className="flex justify-between items-center mb-1">
              <label className="text-[11px] font-medium text-slate-300">
                UTC Timestamp
              </label>
              <button
                type="button"
                onClick={handleSetNow}
                className="text-[10px] text-cyan-400 hover:underline"
              >
                Set to Now
              </button>
            </div>
            <input
              type="text"
              value={timestampInput}
              onChange={(e) => setTimestampInput(e.target.value)}
              placeholder="YYYY-MM-DDTHH:MM:SSZ"
              className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100 focus:outline-none focus:border-cyan-500 font-mono"
            />
            <span className="text-[9px] text-slate-400 block mt-0.5">
              Window: ±45 min (60s sampling)
            </span>
          </div>

          <button
            type="button"
            onClick={() => handleSearch()}
            disabled={loading}
            className="w-full py-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-700 text-white font-medium text-xs rounded transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <LoadingSpinner />
                <span>Propagating Orbit...</span>
              </>
            ) : (
              <span>Load & Propagate</span>
            )}
          </button>
        </div>

        {/* Error message */}
        {error && <ErrorMessage message={error} />}

        {/* Satellite Info Card */}
        {orbitState && (
          <div className="mt-auto">
            <SatelliteInfoPanel
              orbitState={orbitState}
              trajectoryPointCount={trajectory?.points.length}
              onFlyTo={flyToFn || undefined}
            />
          </div>
        )}

        {/* Footer info notice */}
        <div className="text-[10px] text-slate-400 border-t border-slate-800 pt-3">
          <p>
            Frame: <span className="font-mono text-slate-300">TEME</span> converted to Cesium pseudo-fixed Earth-fixed frame via <code className="text-cyan-400">computeTemeToPseudoFixedMatrix</code>.
          </p>
        </div>
      </div>

      {/* Right Globe Viewport — explicit style height so Cesium canvas is non-zero */}
      <div className="flex-1 relative overflow-hidden" style={{ minHeight: '600px' }}>
        <CesiumGlobe
          satelliteState={orbitState}
          trajectoryPoints={trajectory?.points || null}
          onFlyToReady={handleFlyToReady}
        />
      </div>
    </div>
  )
}
