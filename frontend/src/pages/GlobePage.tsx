import React, { useCallback, useEffect, useState } from 'react'
import { getSatellite, getOrbit, multiPropagateSatellites } from '../api/satellites'
import { getTrajectory } from '../api/trajectory'
import { ApiError } from '../api/client'
import type {
  SatelliteGPInfo,
  PropagatedOrbitStateResponse,
  TrajectoryResponse,
  MultiPropagatedObjectState,
  MultiPropagatedOrbitResponse,
} from '../types/api'
import CesiumGlobe from '../components/globe/CesiumGlobe'
import LoadingSpinner from '../components/common/LoadingSpinner'
import ErrorMessage from '../components/common/ErrorMessage'

const QUICK_SATELLITES = [
  { id: 900, name: 'CALSPHERE 1' },
  { id: 25544, name: 'ISS (ZARYA)' },
  { id: 20580, name: 'HUBBLE (HST)' },
]

export default function GlobePage() {
  // Mode: 'catalog' (multi-object) or 'single' (focused analysis)
  const [viewMode, setViewMode] = useState<'catalog' | 'single'>('catalog')

  // Multi-object state
  const [multiData, setMultiData] = useState<MultiPropagatedOrbitResponse | null>(null)
  const [multiLoading, setMultiLoading] = useState(false)
  const [multiError, setMultiError] = useState<string | null>(null)
  const [limitCount, setLimitCount] = useState<number>(50)
  const [regimeFilter, setRegimeFilter] = useState<string>('ALL')
  const [searchFilter, setSearchFilter] = useState<string>('')
  const [selectedNorad, setSelectedNorad] = useState<number | null>(null)
  const [selectedObject, setSelectedObject] = useState<MultiPropagatedObjectState | null>(null)

  // Single satellite state
  const [noradInput, setNoradInput] = useState('25544')
  const [timestampInput, setTimestampInput] = useState(() => new Date().toISOString())
  const [satelliteGP, setSatelliteGP] = useState<SatelliteGPInfo | null>(null)
  const [orbitState, setOrbitState] = useState<PropagatedOrbitStateResponse | null>(null)
  const [trajectory, setTrajectory] = useState<TrajectoryResponse | null>(null)
  const [showOrbitTrack, setShowOrbitTrack] = useState(true)
  const [singleLoading, setSingleLoading] = useState(false)
  const [singleError, setSingleError] = useState<string | null>(null)

  const [flyToFn, setFlyToFn] = useState<(() => void) | null>(null)

  const handleFlyToReady = useCallback((fn: () => void) => {
    setFlyToFn(() => fn)
  }, [])

  // Load multi-object catalogue positions
  const fetchMultiObjects = useCallback(
    (opts?: { limit?: number; regime?: string; search?: string }) => {
      setMultiLoading(true)
      setMultiError(null)

      const lim = opts?.limit ?? limitCount
      const reg = (opts?.regime ?? regimeFilter) === 'ALL' ? undefined : (opts?.regime ?? regimeFilter)
      const q = (opts?.search ?? searchFilter).trim() || undefined

      multiPropagateSatellites({
        limit: lim,
        regime: reg,
        search: q,
      })
        .then((res) => {
          setMultiData(res)
          if (res.objects.length > 0) {
            // Select first object by default if none selected
            setSelectedNorad((prev) => {
              if (prev && res.objects.some((o) => o.norad_cat_id === prev)) {
                return prev
              }
              setSelectedObject(res.objects[0])
              return res.objects[0].norad_cat_id
            })
          }
        })
        .catch((err) => {
          setMultiError(err.message || 'Failed to propagate catalogue objects.')
        })
        .finally(() => {
          setMultiLoading(false)
        })
    },
    [limitCount, regimeFilter, searchFilter],
  )

  // Initial load on mount
  useEffect(() => {
    fetchMultiObjects()
  }, [fetchMultiObjects])

  // When user selects an object from globe or list
  const handleSelectObject = useCallback((noradId: number) => {
    setSelectedNorad(noradId)
    setMultiData((prev) => {
      if (prev) {
        const match = prev.objects.find((o) => o.norad_cat_id === noradId)
        if (match) {
          setSelectedObject(match)
        }
      }
      return prev
    })
  }, [])

  // Load single satellite orbit & trajectory
  async function handleSingleSearch(targetNorad?: number) {
    const noradId = targetNorad !== undefined ? targetNorad : parseInt(noradInput, 10)
    if (isNaN(noradId) || noradId <= 0) {
      setSingleError('Please enter a valid positive NORAD catalog ID.')
      return
    }

    setSingleLoading(true)
    setSingleError(null)

    try {
      const gp = await getSatellite(noradId)
      setSatelliteGP(gp)

      let utcIso = timestampInput.trim()
      if (!utcIso.endsWith('Z') && !utcIso.includes('+') && !utcIso.includes('-')) {
        utcIso += 'Z'
      }

      const orbit = await getOrbit(noradId, utcIso)
      setOrbitState(orbit)

      const targetDate = new Date(utcIso)
      const startDate = new Date(targetDate.getTime() - 45 * 60 * 1000)
      const endDate = new Date(targetDate.getTime() + 45 * 60 * 1000)

      const traj = await getTrajectory(noradId, startDate.toISOString(), endDate.toISOString(), 60.0)
      setTrajectory(traj)
      setSelectedNorad(noradId)
    } catch (err) {
      setSingleError(
        err instanceof ApiError
          ? err.message
          : 'An unexpected error occurred while loading satellite orbit data.',
      )
    } finally {
      setSingleLoading(false)
    }
  }

  // Propagate trajectory for selected catalogue object
  const handlePropagateSelectedTrajectory = () => {
    if (!selectedObject) return
    handleSingleSearch(selectedObject.norad_cat_id)
  }

  return (
    <div
      className="flex flex-col lg:flex-row bg-slate-950 text-slate-100 overflow-hidden"
      style={{ height: '100vh' }}
    >
      {/* Left Sidebar */}
      <div
        className="w-full lg:w-[420px] shrink-0 bg-slate-900 border-r border-slate-800 p-5 flex flex-col gap-4 overflow-y-auto"
        style={{ maxHeight: '100vh' }}
      >
        <div>
          <h1 className="text-xl font-bold text-slate-100">3D Orbital Visualization</h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time analytical SGP4 orbital propagation rendered on CesiumJS globe.
          </p>
        </div>

        {/* View Mode Toggle */}
        <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-medium">
          <button
            type="button"
            onClick={() => setViewMode('catalog')}
            className={`flex-1 py-1.5 rounded-md transition-colors ${
              viewMode === 'catalog'
                ? 'bg-cyan-700 text-white shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Catalogue View ({multiData?.propagated_count ?? 0} Objects)
          </button>
          <button
            type="button"
            onClick={() => setViewMode('single')}
            className={`flex-1 py-1.5 rounded-md transition-colors ${
              viewMode === 'single'
                ? 'bg-cyan-700 text-white shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Single Satellite Focus
          </button>
        </div>

        {/* CATALOGUE VIEW CONTROLS */}
        {viewMode === 'catalog' && (
          <div className="space-y-4">
            {/* Filter controls */}
            <div className="bg-slate-800/80 rounded-lg p-3.5 border border-slate-700/70 space-y-3 text-xs">
              {/* Search */}
              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">
                  Search Object Name / NORAD ID
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && fetchMultiObjects()}
                    placeholder="e.g. STARLINK, ISS, 25544"
                    className="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100 font-mono focus:border-cyan-500 focus:outline-none"
                  />
                  <button
                    onClick={() => fetchMultiObjects()}
                    className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-200 font-medium"
                  >
                    Filter
                  </button>
                </div>
              </div>

              {/* Regime & Limit */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-slate-300 mb-1">
                    Orbital Regime
                  </label>
                  <select
                    value={regimeFilter}
                    onChange={(e) => {
                      setRegimeFilter(e.target.value)
                      fetchMultiObjects({ regime: e.target.value })
                    }}
                    className="w-full px-2 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                  >
                    <option value="ALL">All Regimes</option>
                    <option value="LEO">LEO (&lt;2,000 km)</option>
                    <option value="MEO">MEO (2,000–35k km)</option>
                    <option value="GEO">GEO (~35,786 km)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-slate-300 mb-1">
                    Rendered Count
                  </label>
                  <select
                    value={limitCount}
                    onChange={(e) => {
                      const c = parseInt(e.target.value, 10)
                      setLimitCount(c)
                      fetchMultiObjects({ limit: c })
                    }}
                    className="w-full px-2 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                  >
                    <option value="25">25 objects</option>
                    <option value="50">50 objects (Default)</option>
                    <option value="100">100 objects</option>
                    <option value="200">200 objects (Max)</option>
                  </select>
                </div>
              </div>

              {/* Orbit track toggle */}
              <div className="flex items-center justify-between pt-1 border-t border-slate-700/50">
                <span className="text-slate-400">Show Orbit Trajectory Arc</span>
                <input
                  type="checkbox"
                  checked={showOrbitTrack}
                  onChange={(e) => setShowOrbitTrack(e.target.checked)}
                  className="rounded bg-slate-900 border-slate-700 text-cyan-500 focus:ring-0"
                />
              </div>
            </div>

            {/* Loading & Error */}
            {multiLoading && (
              <div className="flex items-center gap-2.5 text-xs text-slate-400 py-2">
                <LoadingSpinner size="sm" />
                <span>Propagating {limitCount} catalogue objects via SGP4…</span>
              </div>
            )}
            {multiError && <ErrorMessage message={multiError} />}

            {/* Selected Object Detail Card */}
            {selectedObject && (
              <div className="bg-slate-800/90 border border-cyan-800/60 rounded-lg p-3.5 space-y-2 text-xs">
                <div className="flex items-center justify-between pb-2 border-b border-slate-700">
                  <div>
                    <h3 className="font-bold text-slate-100 text-sm">{selectedObject.object_name}</h3>
                    <span className="font-mono text-cyan-400 text-xs">NORAD ID: {selectedObject.norad_cat_id}</span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-cyan-950 text-cyan-300 border border-cyan-800">
                    {selectedObject.classification}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-slate-300">
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <span className="text-[10px] text-slate-400 block">Altitude</span>
                    <span className="font-mono font-bold text-slate-100">
                      {selectedObject.altitude_km.toLocaleString()} km
                    </span>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <span className="text-[10px] text-slate-400 block">Speed</span>
                    <span className="font-mono font-bold text-slate-100">
                      {selectedObject.speed_km_s.toFixed(3)} km/s
                    </span>
                  </div>
                </div>

                <div className="text-[11px] text-slate-400 space-y-1 pt-1 font-mono">
                  <div className="flex justify-between">
                    <span>Coordinates (TEME):</span>
                    <span>[{Math.round(selectedObject.position_x_km)}, {Math.round(selectedObject.position_y_km)}, {Math.round(selectedObject.position_z_km)}] km</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Epoch Age:</span>
                    <span className={selectedObject.is_stale ? 'text-amber-400' : 'text-slate-300'}>
                      {selectedObject.epoch_age_days ? `${selectedObject.epoch_age_days.toFixed(1)}d` : 'Current'}
                      {selectedObject.is_stale && ' (Stale)'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Classification Source:</span>
                    <span className="text-slate-300">{selectedObject.classification_source}</span>
                  </div>
                </div>

                <button
                  onClick={handlePropagateSelectedTrajectory}
                  className="w-full mt-2 py-1.5 bg-cyan-700 hover:bg-cyan-600 text-white rounded text-xs font-medium transition-colors"
                >
                  Propagate 90-min Trajectory Arc
                </button>
              </div>
            )}

            {/* Object List (Scrollable) */}
            {multiData && multiData.objects.length > 0 && (
              <div>
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                  Matching Catalogue Objects ({multiData.objects.length})
                </span>
                <div className="space-y-1 max-h-56 overflow-y-auto pr-1">
                  {multiData.objects.map((obj) => (
                    <button
                      key={obj.norad_cat_id}
                      onClick={() => handleSelectObject(obj.norad_cat_id)}
                      className={`w-full text-left p-2 rounded flex items-center justify-between text-xs transition-colors ${
                        selectedNorad === obj.norad_cat_id
                          ? 'bg-cyan-950 border border-cyan-700 text-cyan-200'
                          : 'bg-slate-800/60 hover:bg-slate-800 border border-slate-700/40 text-slate-300'
                      }`}
                    >
                      <div className="truncate mr-2">
                        <span className="font-semibold block truncate">{obj.object_name}</span>
                        <span className="text-[10px] text-slate-400 font-mono">NORAD {obj.norad_cat_id}</span>
                      </div>
                      <span className="font-mono text-[11px] text-slate-400 shrink-0">
                        {Math.round(obj.altitude_km)} km
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* SINGLE SATELLITE FOCUS CONTROLS */}
        {viewMode === 'single' && (
          <div className="bg-slate-800/70 rounded-lg p-3.5 border border-slate-700/60 space-y-3 text-xs">
            <div>
              <label className="block text-[11px] font-medium text-slate-300 mb-1">
                NORAD Catalog ID
              </label>
              <input
                type="number"
                min="1"
                value={noradInput}
                onChange={(e) => setNoradInput(e.target.value)}
                placeholder="e.g. 25544 (ISS)"
                className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100 font-mono focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {/* Quick presets */}
            <div>
              <span className="text-[10px] text-slate-400 block mb-1">Quick Select:</span>
              <div className="flex flex-wrap gap-1.5">
                {QUICK_SATELLITES.map((sat) => (
                  <button
                    key={sat.id}
                    type="button"
                    onClick={() => {
                      setNoradInput(sat.id.toString())
                      handleSingleSearch(sat.id)
                    }}
                    className="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-[10px] text-cyan-300"
                  >
                    {sat.name}
                  </button>
                ))}
              </div>
            </div>

            {/* UTC Timestamp */}
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="text-[11px] font-medium text-slate-300">UTC Timestamp</label>
                <button
                  type="button"
                  onClick={() => setTimestampInput(new Date().toISOString())}
                  className="text-[10px] text-cyan-400 hover:underline"
                >
                  Set to Now
                </button>
              </div>
              <input
                type="text"
                value={timestampInput}
                onChange={(e) => setTimestampInput(e.target.value)}
                className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100 font-mono focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <button
              onClick={() => handleSingleSearch()}
              disabled={singleLoading}
              className="w-full py-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-700 text-white font-medium rounded text-xs transition-colors flex items-center justify-center gap-2"
            >
              {singleLoading ? <LoadingSpinner size="sm" /> : null}
              <span>{singleLoading ? 'Propagating Orbit…' : 'Load & Propagate'}</span>
            </button>

            {singleError && <ErrorMessage message={singleError} />}
          </div>
        )}

        {/* Data Honesty Notice */}
        <div className="mt-auto pt-3 border-t border-slate-800 text-[10px] text-slate-400 space-y-1">
          <p className="font-semibold text-slate-400">Data Coverage & Astrodynamics Notice:</p>
          <p>
            Current local catalogue contains active satellites from CelesTrak GP dataset. Debris and rocket bodies are not currently ingested.
            Positions are calculated via analytical SGP4 propagation (not real-time radar tracks).
          </p>
        </div>
      </div>

      {/* 3D Cesium Viewport */}
      <div className="flex-1 relative overflow-hidden" style={{ minHeight: '600px' }}>
        <CesiumGlobe
          satelliteState={orbitState}
          trajectoryPoints={trajectory?.points || null}
          multiObjects={multiData?.objects || null}
          selectedNoradId={selectedNorad}
          showOrbitTrack={showOrbitTrack}
          timestampIso={multiData?.timestamp}
          onSelectObject={handleSelectObject}
          onFlyToReady={handleFlyToReady}
        />
      </div>
    </div>
  )
}
