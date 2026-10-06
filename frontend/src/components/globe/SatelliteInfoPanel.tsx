import React from 'react'
import type { PropagatedOrbitStateResponse } from '../../types/api'

interface SatelliteInfoPanelProps {
  orbitState: PropagatedOrbitStateResponse | null
  trajectoryPointCount?: number
  onFlyTo?: () => void
}

export default function SatelliteInfoPanel({
  orbitState,
  trajectoryPointCount,
  onFlyTo,
}: SatelliteInfoPanelProps) {
  if (!orbitState) return null

  const {
    norad_cat_id,
    object_name,
    timestamp,
    position_x_km,
    position_y_km,
    position_z_km,
    velocity_x_km_s,
    velocity_y_km_s,
    velocity_z_km_s,
    sgp4_error,
    error_message,
  } = orbitState

  // Derived orbital metrics
  const radiusKm = Math.sqrt(
    position_x_km ** 2 + position_y_km ** 2 + position_z_km ** 2,
  )
  const approxAltKm = radiusKm - 6371.0 // Mean Earth radius: 6371 km
  const speedKmS = Math.sqrt(
    velocity_x_km_s ** 2 + velocity_y_km_s ** 2 + velocity_z_km_s ** 2,
  )

  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-lg p-4 shadow-xl backdrop-blur-md max-w-sm w-full text-slate-100 text-xs">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700/80 pb-2.5 mb-3">
        <div>
          <span className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400">
            NORAD {norad_cat_id}
          </span>
          <h2 className="text-sm font-bold text-slate-100 truncate max-w-[200px]" title={object_name}>
            {object_name}
          </h2>
        </div>
        {onFlyTo && (
          <button
            type="button"
            onClick={onFlyTo}
            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-600 text-cyan-300 text-[11px] font-medium transition-colors"
          >
            Fly To
          </button>
        )}
      </div>

      {/* SGP4 Error notice if non-zero */}
      {sgp4_error !== 0 && (
        <div className="mb-3 p-2 rounded bg-amber-950/60 border border-amber-800 text-amber-300">
          <p className="font-semibold text-[11px]">SGP4 Warning (Code {sgp4_error})</p>
          <p className="text-[10px] text-amber-400/90">{error_message || 'Propagation issue detected at this epoch'}</p>
        </div>
      )}

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="bg-slate-800/80 rounded p-2 border border-slate-700/50">
          <span className="text-[10px] text-slate-400 block">Orbital Radius</span>
          <span className="text-xs font-mono font-medium text-slate-200">
            {radiusKm.toFixed(1)} <span className="text-[10px] text-slate-400">km</span>
          </span>
        </div>

        <div className="bg-slate-800/80 rounded p-2 border border-slate-700/50">
          <span className="text-[10px] text-slate-400 block">Speed</span>
          <span className="text-xs font-mono font-medium text-slate-200">
            {speedKmS.toFixed(3)} <span className="text-[10px] text-slate-400">km/s</span>
          </span>
        </div>

        <div className="col-span-2 bg-slate-800/80 rounded p-2 border border-slate-700/50">
          <div className="flex justify-between items-baseline">
            <span className="text-[10px] text-slate-400">Approx. Altitude</span>
            <span className="text-xs font-mono font-medium text-cyan-300">
              {approxAltKm.toFixed(1)} km
            </span>
          </div>
          <p className="text-[9px] text-slate-400 mt-1 leading-tight italic">
            Approximate altitude above mean Earth radius (6371 km). Not a high-precision geodetic altitude.
          </p>
        </div>
      </div>

      {/* Position Vector (TEME) */}
      <div className="mb-2 bg-slate-800/50 rounded p-2 border border-slate-700/40">
        <span className="text-[10px] text-slate-400 block mb-1">
          TEME Position Vector (km)
        </span>
        <div className="grid grid-cols-3 gap-1 text-[11px] font-mono text-slate-300">
          <div><span className="text-slate-500">X:</span> {position_x_km.toFixed(1)}</div>
          <div><span className="text-slate-500">Y:</span> {position_y_km.toFixed(1)}</div>
          <div><span className="text-slate-500">Z:</span> {position_z_km.toFixed(1)}</div>
        </div>
      </div>

      {/* Footer Timestamp & Info */}
      <div className="pt-2 border-t border-slate-700/60 flex flex-col gap-1 text-[10px] text-slate-400">
        <div className="flex justify-between">
          <span>Propagation Time (UTC):</span>
          <span className="font-mono text-slate-300">{timestamp}</span>
        </div>
        {trajectoryPointCount !== undefined && (
          <div className="flex justify-between">
            <span>Trajectory Samples:</span>
            <span className="font-mono text-slate-300">{trajectoryPointCount} points</span>
          </div>
        )}
      </div>
    </div>
  )
}
