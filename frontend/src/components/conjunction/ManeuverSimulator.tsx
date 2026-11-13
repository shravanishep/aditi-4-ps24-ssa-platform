import { useState, useId } from 'react'
import { simulateManeuver } from '../../api/maneuver'
import { logEvent } from '../../api/events'
import { ApiError } from '../../api/client'
import type { ManeuverSimulationResponse } from '../../types/api'
import LoadingSpinner from '../common/LoadingSpinner'
import ErrorMessage from '../common/ErrorMessage'

interface ManeuverSimulatorProps {
  norad1: number
  norad2: number
  defaultManeuverTime: string
  satellite1Name?: string
  satellite2Name?: string
  windowStart?: string
  windowEnd?: string
  tca?: string
}

export default function ManeuverSimulator({
  norad1,
  norad2,
  defaultManeuverTime,
  satellite1Name = 'Protected Satellite',
  satellite2Name = 'Threat Object',
  windowStart,
  windowEnd,
  tca,
}: ManeuverSimulatorProps) {
  // Convert ISO time to local input format YYYY-MM-DDTHH:mm
  const formatForInput = (isoStr: string) => {
    try {
      const dt = new Date(isoStr)
      // Default to 1 hour before TCA if valid
      const maneuverDt = new Date(dt.getTime() - 60 * 60 * 1000)
      return maneuverDt.toISOString().slice(0, 16)
    } catch {
      return new Date().toISOString().slice(0, 16)
    }
  }

  const [maneuverTime, setManeuverTime] = useState(() => formatForInput(defaultManeuverTime))

  // User inputs in METERS PER SECOND (m/s) — standard for space operations
  const [dvX_ms, setDvX_ms] = useState<number>(0.0)
  const [dvY_ms, setDvY_ms] = useState<number>(5.0) // 5.0 m/s along-track default
  const [dvZ_ms, setDvZ_ms] = useState<number>(0.0)
  const [windowHours, setWindowHours] = useState<number>(24.0)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ManeuverSimulationResponse | null>(null)
  const [loggedStatus, setLoggedStatus] = useState<string | null>(null)

  // Calculate total Delta-V in m/s dynamically from components
  const totalDvMs = Math.sqrt(dvX_ms ** 2 + dvY_ms ** 2 + dvZ_ms ** 2)
  const totalDvKmS = totalDvMs / 1000.0

  // Validate maneuver time against conjunction search window & TCA
  const validateManeuverTime = (): { valid: boolean; warning?: string } => {
    try {
      const mTime = new Date(maneuverTime).getTime()
      if (isNaN(mTime)) return { valid: false, warning: 'Invalid maneuver timestamp.' }

      if (tca) {
        const tcaTime = new Date(tca).getTime()
        if (mTime > tcaTime) {
          return {
            valid: false,
            warning: 'Maneuver time is scheduled AFTER the predicted TCA. Avoidance burns must occur prior to closest approach to alter the encounter geometry.',
          }
        }
      }

      if (windowStart) {
        const wStart = new Date(windowStart).getTime()
        if (mTime < wStart - 3600 * 1000) {
          return {
            valid: true,
            warning: 'Notice: Maneuver time precedes the conjunction search window start.',
          }
        }
      }

      return { valid: true }
    } catch {
      return { valid: true }
    }
  }

  const timeValidation = validateManeuverTime()

  async function handleSimulate(e: React.FormEvent) {
    e.preventDefault()
    if (!timeValidation.valid) {
      setError(timeValidation.warning || 'Please specify a valid maneuver time before TCA.')
      return
    }

    setLoading(true)
    setError(null)
    setLoggedStatus(null)

    try {
      const isoUtcTime = new Date(maneuverTime).toISOString()
      // Convert m/s inputs to km/s for backend orbital simulation API
      const data = await simulateManeuver({
        norad1,
        norad2,
        maneuver_time: isoUtcTime,
        dv_x_km_s: dvX_ms / 1000.0,
        dv_y_km_s: dvY_ms / 1000.0,
        dv_z_km_s: dvZ_ms / 1000.0,
        window_hours: windowHours,
      })
      setResult(data)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Simulation Error (${err.status}): ${err.message}`)
      } else {
        setError('CAM simulation failed. Verify backend numerical propagation parameters.')
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleLogToTimeline() {
    if (!result) return
    try {
      await logEvent({
        norad_id: norad1,
        object_name: satellite1Name,
        event_type: 'CONJUNCTION',
        classification: result.improvement_km > 0 ? 'STATION_KEEPING' : 'UNKNOWN',
        classification_explanation: `Simulated CAM: applied ΔV=${(result.dv_magnitude_km_s * 1000).toFixed(1)} m/s, miss distance changed from ${result.original_miss_km.toFixed(3)} km to ${result.modified_miss_km.toFixed(3)} km.`,
        tca: result.modified_tca,
        miss_distance_km: result.modified_miss_km,
        rel_speed_km_s: result.modified_rel_speed_km_s,
      })
      setLoggedStatus('Event recorded in persistent timeline.')
    } catch (err) {
      setLoggedStatus('Failed to log event.')
    }
  }

  const timeInputId = useId()
  const dvXInputId = useId()
  const dvYInputId = useId()
  const dvZInputId = useId()
  const windowInputId = useId()

  return (
    <div className="border border-slate-700 bg-slate-900 rounded-lg p-6 space-y-6">
      {/* Title & Scope Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <span className="text-sky-400 font-mono">⚡</span> Collision Avoidance Maneuver (CAM) Simulator
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Simulate an impulsive velocity change (ΔV) for {satellite1Name} (#{norad1}) and propagate post-maneuver trajectory with numerical 4th-order Runge-Kutta (RK4) two-body + J2 geopotential integration.
          </p>
        </div>
        <span className="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono self-start sm:self-auto">
          Numerical Propagator
        </span>
      </div>

      {/* Coordinate Frame Explanation Card */}
      <div className="bg-slate-800/60 border border-slate-700/80 rounded-lg p-3.5 text-xs text-slate-300 space-y-1.5">
        <span className="font-semibold text-slate-200 block">
          Coordinate Frame: True Equator, Mean Equinox (TEME) Inertial Cartesian
        </span>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-slate-400 pt-1">
          <div>
            <strong className="text-slate-300">ΔVx (Radial):</strong> Displaces along satellite position vector (inward/outward).
          </div>
          <div>
            <strong className="text-slate-300">ΔVy (Along-Track):</strong> Aligned with velocity vector. Most fuel-effective for expanding separation phasing.
          </div>
          <div>
            <strong className="text-slate-300">ΔVz (Cross-Track):</strong> Normal to orbital plane. Changes inclination and node (fuel intensive).
          </div>
        </div>
      </div>

      {/* Simulator Form */}
      <form onSubmit={handleSimulate} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Maneuver Time */}
          <div>
            <label htmlFor={timeInputId} className="block text-xs font-medium text-slate-300 mb-1">
              Maneuver Epoch (UTC)
            </label>
            <input
              id={timeInputId}
              type="datetime-local"
              value={maneuverTime}
              onChange={(e) => setManeuverTime(e.target.value)}
              required
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
            />
            <span className="text-[10px] text-slate-500 mt-0.5 block">
              Default: 1h prior to nominal TCA
            </span>
          </div>

          {/* Delta-V Components in m/s */}
          <div className="lg:col-span-2">
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Impulsive ΔV Components [meters / second] (TEME frame)
            </label>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <div className="text-[10px] text-slate-400 mb-0.5 font-mono">ΔVx (Radial)</div>
                <input
                  id={dvXInputId}
                  type="number"
                  step="0.1"
                  value={dvX_ms}
                  onChange={(e) => setDvX_ms(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-sky-500"
                  placeholder="0.0 m/s"
                />
              </div>
              <div>
                <div className="text-[10px] text-slate-400 mb-0.5 font-mono">ΔVy (Along-track)</div>
                <input
                  id={dvYInputId}
                  type="number"
                  step="0.1"
                  value={dvY_ms}
                  onChange={(e) => setDvY_ms(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-sky-500"
                  placeholder="5.0 m/s"
                />
              </div>
              <div>
                <div className="text-[10px] text-slate-400 mb-0.5 font-mono">ΔVz (Cross-track)</div>
                <input
                  id={dvZInputId}
                  type="number"
                  step="0.1"
                  value={dvZ_ms}
                  onChange={(e) => setDvZ_ms(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-sky-500"
                  placeholder="0.0 m/s"
                />
              </div>
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-400 mt-1 font-mono">
              <span>
                Total ΔV: <strong className="text-sky-400">{totalDvMs.toFixed(2)} m/s</strong> ({totalDvKmS.toFixed(5)} km/s)
              </span>
              {totalDvMs === 0 && (
                <span className="text-amber-400/90 text-[10px]">Zero burn (no maneuver applied)</span>
              )}
            </div>
          </div>

          {/* Propagation Window */}
          <div>
            <label htmlFor={windowInputId} className="block text-xs font-medium text-slate-300 mb-1">
              Simulation Window (Hours)
            </label>
            <input
              id={windowInputId}
              type="number"
              min="1"
              max="72"
              step="1"
              value={windowHours}
              onChange={(e) => setWindowHours(parseFloat(e.target.value) || 24)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-sky-500"
            />
            <span className="text-[10px] text-slate-500 mt-0.5 block">
              Numerical step: 30s
            </span>
          </div>
        </div>

        {/* Validation warning */}
        {timeValidation.warning && (
          <div className="text-xs text-amber-300/90 bg-amber-950/30 border border-amber-800/60 p-2.5 rounded">
            ⚠️ {timeValidation.warning}
          </div>
        )}

        {/* Action Button */}
        <div>
          <button
            type="submit"
            disabled={loading || !timeValidation.valid}
            className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-medium px-5 py-2 rounded text-xs transition-colors flex items-center justify-center gap-2"
          >
            {loading ? <LoadingSpinner size="sm" /> : 'Run Avoidance Simulation'}
          </button>
        </div>
      </form>

      {error && <ErrorMessage message={error} />}

      {/* Result Comparison */}
      {result && (
        <div className="border-t border-slate-800 pt-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-200">
              Maneuver Simulation Outcome
            </h3>
            <span
              className={`text-xs px-3 py-1 rounded font-medium border ${
                result.improvement_km > 0
                  ? 'bg-emerald-950/80 text-emerald-400 border-emerald-700/60'
                  : 'bg-rose-950/80 text-rose-400 border-rose-700/60'
              }`}
            >
              {result.improvement_km > 0
                ? `Separation Improved (+${result.improvement_km.toFixed(3)} km)`
                : `Separation Deteriorated (${result.improvement_km.toFixed(3)} km)`}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Nominal Pre-Maneuver */}
            <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 space-y-2.5 text-xs">
              <p className="font-semibold text-slate-300 border-b border-slate-700 pb-1.5 flex items-center justify-between">
                <span>Before Maneuver (Nominal SGP4)</span>
                <span className="text-[10px] text-slate-500 font-mono">Unmodified</span>
              </p>
              <div className="flex justify-between text-slate-400">
                <span>Predicted TCA:</span>
                <span className="font-mono text-slate-200">{new Date(result.original_tca).toUTCString()}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Miss Distance:</span>
                <span className="font-mono text-amber-300 font-bold">{result.original_miss_km.toFixed(3)} km</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Relative Velocity:</span>
                <span className="font-mono text-slate-200">{result.original_rel_speed_km_s.toFixed(3)} km/s</span>
              </div>
            </div>

            {/* Modified Post-Maneuver */}
            <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 space-y-2.5 text-xs">
              <p className="font-semibold text-sky-300 border-b border-slate-700 pb-1.5 flex items-center justify-between">
                <span>After Maneuver (RK4 Two-Body + J2)</span>
                <span className="text-[10px] text-sky-400 font-mono">ΔV Applied</span>
              </p>
              <div className="flex justify-between text-slate-400">
                <span>New Predicted TCA:</span>
                <span className="font-mono text-slate-200">{new Date(result.modified_tca).toUTCString()}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>New Miss Distance:</span>
                <span className="font-mono text-sky-300 font-bold">{result.modified_miss_km.toFixed(3)} km</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Relative Velocity:</span>
                <span className="font-mono text-slate-200">{result.modified_rel_speed_km_s.toFixed(3)} km/s</span>
              </div>
            </div>
          </div>

          {/* Explanation of change */}
          <div className="bg-slate-800/40 border border-slate-700/60 rounded p-3 text-xs text-slate-300">
            {result.improvement_km > 0 ? (
              <p>
                ✓ <strong className="text-emerald-400">Positive Clearance:</strong> The applied velocity change of {(result.dv_magnitude_km_s * 1000).toFixed(1)} m/s increased the minimum miss distance by {result.improvement_km.toFixed(3)} km, widening orbital separation between the objects at closest approach.
              </p>
            ) : (
              <p>
                ⚠️ <strong className="text-rose-400">Negative Separation:</strong> The applied velocity change reduced the minimum miss distance by {Math.abs(result.improvement_km).toFixed(3)} km. In operational planning, this burn direction or magnitude would be rejected.
              </p>
            )}
          </div>

          {/* Footer & Timeline Logging */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-400 pt-2 border-t border-slate-800">
            <span>
              Applied ΔV: <span className="font-mono text-slate-200">{(result.dv_magnitude_km_s * 1000).toFixed(2)} m/s</span> |
              Trajectory steps: <span className="font-mono text-slate-200">{result.modified_trajectory.length}</span> numerical points
            </span>

            <div className="flex items-center gap-3">
              {loggedStatus && (
                <span className="text-emerald-400 text-xs">{loggedStatus}</span>
              )}
              <button
                type="button"
                onClick={handleLogToTimeline}
                className="bg-slate-800 hover:bg-slate-700 text-slate-300 px-3.5 py-1.5 rounded text-xs border border-slate-600 transition-colors"
              >
                Log Maneuver to Timeline
              </button>
            </div>
          </div>

          <p className="text-[11px] text-slate-500 italic">
            Advisory Notice: {result.disclaimer}
          </p>
        </div>
      )}
    </div>
  )
}
