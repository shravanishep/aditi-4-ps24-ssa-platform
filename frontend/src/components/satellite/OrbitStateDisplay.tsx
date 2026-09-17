import type { PropagatedOrbitStateResponse } from '../../types/api'
import InfoCard from '../common/InfoCard'

export default function OrbitStateDisplay({ data }: { data: PropagatedOrbitStateResponse }) {
  const sgp4Ok = data.sgp4_error === 0

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h4 className="text-slate-200 font-medium">Propagated State</h4>
        <span
          className={`text-xs px-2 py-0.5 rounded-full border ${
            sgp4Ok
              ? 'bg-green-900 text-green-400 border-green-700'
              : 'bg-red-900 text-red-400 border-red-700'
          }`}
        >
          SGP4 {sgp4Ok ? 'OK' : `Error ${data.sgp4_error}`}
        </span>
      </div>

      <InfoCard
        label="Timestamp (UTC)"
        value={new Date(data.timestamp).toISOString()}
        mono
      />

      {data.error_message && (
        <p className="text-yellow-400 text-xs bg-yellow-950 border border-yellow-800 rounded px-3 py-2">
          {data.error_message}
        </p>
      )}

      <div>
        <p className="text-xs text-slate-400 mb-2 uppercase tracking-wider">
          Position — TEME (km)
        </p>
        <div className="grid grid-cols-3 gap-2">
          <InfoCard label="X (km)" value={data.position_x_km.toFixed(3)} mono />
          <InfoCard label="Y (km)" value={data.position_y_km.toFixed(3)} mono />
          <InfoCard label="Z (km)" value={data.position_z_km.toFixed(3)} mono />
        </div>
      </div>

      <div>
        <p className="text-xs text-slate-400 mb-2 uppercase tracking-wider">
          Velocity — TEME (km/s)
        </p>
        <div className="grid grid-cols-3 gap-2">
          <InfoCard label="VX (km/s)" value={data.velocity_x_km_s.toFixed(6)} mono />
          <InfoCard label="VY (km/s)" value={data.velocity_y_km_s.toFixed(6)} mono />
          <InfoCard label="VZ (km/s)" value={data.velocity_z_km_s.toFixed(6)} mono />
        </div>
      </div>
    </div>
  )
}
