import { useState } from 'react'
import { getSatellite, getOrbit } from '../api/satellites'
import { ApiError } from '../api/client'
import type { SatelliteGPInfo, PropagatedOrbitStateResponse } from '../types/api'
import SatelliteSearchForm from '../components/satellite/SatelliteSearchForm'
import SatelliteInfo from '../components/satellite/SatelliteInfo'
import OrbitRequestForm from '../components/satellite/OrbitRequestForm'
import OrbitStateDisplay from '../components/satellite/OrbitStateDisplay'
import LoadingSpinner from '../components/common/LoadingSpinner'
import ErrorMessage from '../components/common/ErrorMessage'

export default function SatelliteExplorerPage() {
  const [satelliteData, setSatelliteData] = useState<SatelliteGPInfo | null>(null)
  const [satelliteLoading, setSatelliteLoading] = useState(false)
  const [satelliteError, setSatelliteError] = useState<string | null>(null)

  const [orbitData, setOrbitData] = useState<PropagatedOrbitStateResponse | null>(null)
  const [orbitLoading, setOrbitLoading] = useState(false)
  const [orbitError, setOrbitError] = useState<string | null>(null)

  async function handleSearch(noradId: number) {
    setSatelliteLoading(true)
    setSatelliteError(null)
    setSatelliteData(null)
    setOrbitData(null)
    setOrbitError(null)
    try {
      const data = await getSatellite(noradId)
      setSatelliteData(data)
    } catch (err) {
      setSatelliteError(
        err instanceof ApiError ? err.message : 'Unexpected error loading satellite.',
      )
    } finally {
      setSatelliteLoading(false)
    }
  }

  async function handlePropagate(timestamp: string) {
    if (!satelliteData) return
    setOrbitLoading(true)
    setOrbitError(null)
    setOrbitData(null)
    try {
      const data = await getOrbit(satelliteData.norad_cat_id, timestamp)
      setOrbitData(data)
    } catch (err) {
      setOrbitError(
        err instanceof ApiError ? err.message : 'Unexpected error during propagation.',
      )
    } finally {
      setOrbitLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-xl font-bold text-slate-100 mb-1">Satellite Explorer</h1>
      <p className="text-slate-400 text-sm mb-6">
        Search by NORAD catalog ID to view GP orbital parameters and propagate to a requested UTC time.
      </p>

      {/* Search */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 mb-6">
        <SatelliteSearchForm onSearch={handleSearch} loading={satelliteLoading} />
      </div>

      {/* Satellite loading */}
      {satelliteLoading && (
        <div className="flex items-center gap-3 text-slate-400 text-sm mb-6">
          <LoadingSpinner size="sm" />
          <span>Looking up satellite…</span>
        </div>
      )}

      {/* Satellite error */}
      {satelliteError && (
        <div className="mb-6">
          <ErrorMessage message={satelliteError} />
        </div>
      )}

      {/* Satellite data */}
      {satelliteData && (
        <>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 mb-6">
            <SatelliteInfo data={satelliteData} />
          </div>

          {/* Propagation */}
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 mb-6">
            <h3 className="text-slate-300 font-medium mb-4">Propagate Orbit</h3>
            <OrbitRequestForm onPropagate={handlePropagate} loading={orbitLoading} />
          </div>

          {orbitLoading && (
            <div className="flex items-center gap-3 text-slate-400 text-sm mb-6">
              <LoadingSpinner size="sm" />
              <span>Propagating…</span>
            </div>
          )}

          {orbitError && (
            <div className="mb-6">
              <ErrorMessage message={orbitError} />
            </div>
          )}

          {orbitData && (
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <OrbitStateDisplay data={orbitData} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
