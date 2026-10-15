import { useState } from 'react'
import type { SatelliteGPInfo } from '../../types/api'

interface Props {
  data: SatelliteGPInfo
}

interface ParamExplanation {
  label: string
  unit: string
  explanation: string
  example?: string
}

const PARAM_GUIDE: Record<string, ParamExplanation> = {
  epoch: {
    label: 'Orbital Epoch',
    unit: 'UTC Timestamp',
    explanation:
      'The exact date and time when this set of orbital elements was observed and calculated. SGP4 propagation accuracy decays with epoch age.',
    example: 'Older than 14 days is flagged as stale orbital data.',
  },
  mean_motion: {
    label: 'Mean Motion',
    unit: 'revolutions / day',
    explanation:
      'The number of complete orbits the satellite completes around Earth per day. Higher mean motion corresponds to lower altitude.',
    example: '~15.5 rev/day for ISS in LEO (~400 km); ~1.0 rev/day for GEO (~35,786 km).',
  },
  eccentricity: {
    label: 'Eccentricity',
    unit: 'dimensionless (0–1)',
    explanation:
      'Describes the geometric shape of the orbit. A value of 0 is a circular orbit; values between 0 and 1 are elliptical.',
    example: '< 0.01 is near-circular; > 0.25 indicates a highly elliptical orbit (HEO/Molniya).',
  },
  inclination: {
    label: 'Inclination',
    unit: 'degrees (°)',
    explanation:
      'Tilt angle of the orbital plane relative to Earth’s equatorial plane. 0° is equatorial, 90° is polar, and >90° is retrograde.',
    example: '51.6° for ISS, 97.5° for Sun-synchronous Earth observation satellites.',
  },
  ra_of_asc_node: {
    label: 'Right Ascension of Ascending Node (RAAN)',
    unit: 'degrees (°)',
    explanation:
      'The angle in the equatorial plane from the vernal equinox to the point where the satellite crosses from the southern to northern hemisphere.',
    example: 'Defines the spatial orientation of the orbital plane in inertial space.',
  },
  arg_of_pericenter: {
    label: 'Argument of Perigee',
    unit: 'degrees (°)',
    explanation:
      'The angular distance from the ascending node to the orbit’s point of closest approach to Earth (perigee), measured in the orbital plane.',
    example: 'Locates the lowest point of the orbit relative to the Earth equator crossing.',
  },
  mean_anomaly: {
    label: 'Mean Anomaly',
    unit: 'degrees (°)',
    explanation:
      'Mathematical parameter indicating the satellite’s position along its orbit relative to perigee at the epoch time, assuming uniform angular motion.',
    example: '0° means the satellite is at perigee; 180° means it is at apogee.',
  },
  bstar: {
    label: 'BSTAR Drag Term',
    unit: '1 / Earth-radii',
    explanation:
      'An SGP4 mathematical drag parameter combining ballistic coefficient and atmospheric density. It is NOT a direct physical drag measurement.',
    example: 'Small positive values indicate natural atmospheric drag orbital decay.',
  },
  mean_motion_dot: {
    label: 'First Derivative of Mean Motion',
    unit: 'rev / day²',
    explanation:
      'Rate of change of mean motion over time (ballistic drag acceleration or decay rate).',
    example: 'Positive values indicate the satellite is spiraling inward due to atmospheric drag.',
  },
  mean_motion_ddot: {
    label: 'Second Derivative of Mean Motion',
    unit: 'rev / day³',
    explanation:
      'Second time derivative of mean motion, representing higher-order atmospheric drag variations. Often 0.0 in standard GP data.',
  },
}

export default function SatelliteInfo({ data }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [activeTooltip, setActiveTooltip] = useState<string | null>(null)

  // Derived orbital mechanics
  const meanMotion = data.mean_motion
  const ecc = data.eccentricity
  const periodMinutes = meanMotion > 0 ? (1440.0 / meanMotion) : 0

  // Standard gravitational parameter mu (km^3/s^2)
  const mu = 398600.4418
  const nRadPerSec = (meanMotion * 2.0 * Math.PI) / 86400.0
  const semiMajorAxisKm = nRadPerSec > 0 ? Math.cbrt(mu / (nRadPerSec * nRadPerSec)) : 0
  const perigeeAltitudeKm = semiMajorAxisKm > 0 ? semiMajorAxisKm * (1.0 - ecc) - 6378.137 : 0
  const apogeeAltitudeKm = semiMajorAxisKm > 0 ? semiMajorAxisKm * (1.0 + ecc) - 6378.137 : 0
  const meanAltitudeKm = (perigeeAltitudeKm + apogeeAltitudeKm) / 2.0

  // Epoch age
  let epochAgeDays: number | null = null
  let isStale = false
  if (data.epoch) {
    try {
      const epochTime = new Date(data.epoch).getTime()
      if (!isNaN(epochTime)) {
        epochAgeDays = Math.round(((Date.now() - epochTime) / (1000 * 86400)) * 10) / 10
        isStale = epochAgeDays > 14
      }
    } catch {
      // ignore parse failure
    }
  }

  // Regime classification
  let regimeName = 'Low Earth Orbit (LEO)'
  let regimeColor = 'text-cyan-400 bg-cyan-950/60 border-cyan-800'
  if (meanAltitudeKm >= 35500 && meanAltitudeKm <= 36500) {
    regimeName = 'Geostationary Orbit (GEO)'
    regimeColor = 'text-emerald-400 bg-emerald-950/60 border-emerald-800'
  } else if (meanAltitudeKm >= 2000) {
    regimeName = 'Medium Earth Orbit (MEO)'
    regimeColor = 'text-blue-400 bg-blue-950/60 border-blue-800'
  } else if (ecc > 0.25 || apogeeAltitudeKm > 20000) {
    regimeName = 'High Elliptical Orbit (HEO)'
    regimeColor = 'text-purple-400 bg-purple-950/60 border-purple-800'
  }

  const renderParamTooltip = (key: string) => {
    const info = PARAM_GUIDE[key]
    if (!info) return null
    return (
      <button
        type="button"
        onClick={() => setActiveTooltip(activeTooltip === key ? null : key)}
        className="text-slate-400 hover:text-cyan-300 ml-1.5 focus:outline-none transition-colors"
        title="View parameter explanation"
      >
        <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full border border-slate-600 text-[10px] font-mono font-bold leading-none">
          ?
        </span>
      </button>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-700/80">
        <div>
          <div className="flex items-center gap-2.5">
            <h3 className="text-xl font-bold text-slate-100">{data.object_name}</h3>
            <span
              className={`text-xs px-2.5 py-0.5 rounded-full border font-semibold ${regimeColor}`}
            >
              {regimeName}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400 mt-1 font-mono">
            <span>NORAD ID: <strong className="text-cyan-400">{data.norad_cat_id}</strong></span>
            {data.object_id && (
              <span>· COSPAR: <strong className="text-slate-300">{data.object_id}</strong></span>
            )}
          </div>
        </div>

        {epochAgeDays !== null && (
          <div className="text-right">
            <span
              className={`text-xs font-mono px-2 py-0.5 rounded border ${
                isStale
                  ? 'bg-amber-950/80 text-amber-300 border-amber-700'
                  : 'bg-slate-800 text-slate-300 border-slate-700'
              }`}
            >
              {isStale ? `⚠ Epoch: ${epochAgeDays}d old (Stale)` : `Epoch: ${epochAgeDays}d old`}
            </span>
            <p className="text-[10px] text-slate-500 mt-1 font-mono truncate max-w-xs">
              {data.epoch}
            </p>
          </div>
        )}
      </div>

      {/* Parameter Explanation Modal/Card when active */}
      {activeTooltip && PARAM_GUIDE[activeTooltip] && (
        <div className="bg-slate-900 border border-cyan-800/80 rounded-lg p-3.5 text-xs animate-fadeIn">
          <div className="flex items-center justify-between text-cyan-300 font-semibold mb-1">
            <span className="flex items-center gap-1.5">
              <span>ℹ</span>
              <span>{PARAM_GUIDE[activeTooltip].label}</span>
              <span className="text-[11px] text-slate-400 font-normal">
                ({PARAM_GUIDE[activeTooltip].unit})
              </span>
            </span>
            <button
              onClick={() => setActiveTooltip(null)}
              className="text-slate-400 hover:text-white"
            >
              ✕
            </button>
          </div>
          <p className="text-slate-300 leading-relaxed">
            {PARAM_GUIDE[activeTooltip].explanation}
          </p>
          {PARAM_GUIDE[activeTooltip].example && (
            <p className="text-slate-400 text-[11px] mt-1.5 font-mono">
              Typical value: {PARAM_GUIDE[activeTooltip].example}
            </p>
          )}
        </div>
      )}

      {/* Friendly Summary Cards */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
          Orbital Profile Summary
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {/* Altitude */}
          <div className="bg-slate-900/80 border border-slate-700 rounded-lg p-3">
            <div className="flex items-center text-xs text-slate-400 mb-1">
              <span>Mean Altitude</span>
            </div>
            <div className="text-lg font-bold font-mono text-cyan-300">
              {meanAltitudeKm > 0 ? `${Math.round(meanAltitudeKm).toLocaleString()} km` : 'N/A'}
            </div>
            <div className="text-[10px] font-mono text-slate-400 mt-1">
              Perigee: {Math.round(perigeeAltitudeKm).toLocaleString()} km<br />
              Apogee: {Math.round(apogeeAltitudeKm).toLocaleString()} km
            </div>
          </div>

          {/* Period */}
          <div className="bg-slate-900/80 border border-slate-700 rounded-lg p-3">
            <div className="flex items-center text-xs text-slate-400 mb-1">
              <span>Orbital Period</span>
              {renderParamTooltip('mean_motion')}
            </div>
            <div className="text-lg font-bold font-mono text-slate-100">
              {periodMinutes > 0 ? `${periodMinutes.toFixed(1)} min` : 'N/A'}
            </div>
            <div className="text-[10px] font-mono text-slate-400 mt-1">
              {data.mean_motion.toFixed(4)} rev/day
            </div>
          </div>

          {/* Inclination */}
          <div className="bg-slate-900/80 border border-slate-700 rounded-lg p-3">
            <div className="flex items-center text-xs text-slate-400 mb-1">
              <span>Inclination</span>
              {renderParamTooltip('inclination')}
            </div>
            <div className="text-lg font-bold font-mono text-slate-100">
              {data.inclination.toFixed(2)}°
            </div>
            <div className="text-[10px] font-mono text-slate-400 mt-1">
              {data.inclination < 15 ? 'Equatorial' : data.inclination > 80 && data.inclination < 100 ? 'Polar' : 'Inclined'}
            </div>
          </div>

          {/* Orbit Shape / Eccentricity */}
          <div className="bg-slate-900/80 border border-slate-700 rounded-lg p-3">
            <div className="flex items-center text-xs text-slate-400 mb-1">
              <span>Orbit Shape</span>
              {renderParamTooltip('eccentricity')}
            </div>
            <div className="text-lg font-bold font-mono text-slate-100">
              {ecc < 0.005 ? 'Circular' : 'Elliptical'}
            </div>
            <div className="text-[10px] font-mono text-slate-400 mt-1">
              e = {data.eccentricity.toFixed(5)}
            </div>
          </div>
        </div>
      </div>

      {/* Altitude Indicator Profile Bar */}
      <div className="bg-slate-900/70 border border-slate-700/80 rounded-lg p-3.5 space-y-2">
        <div className="flex justify-between items-center text-xs">
          <span className="font-semibold text-slate-300">Orbital Regime Gauge</span>
          <span className="text-slate-400 font-mono text-[11px]">
            Target: ~{Math.round(meanAltitudeKm).toLocaleString()} km altitude
          </span>
        </div>
        <div className="w-full bg-slate-800 rounded-full h-3 overflow-hidden flex relative border border-slate-700">
          <div className="w-[35%] bg-cyan-900/50 border-r border-slate-700 flex items-center justify-center text-[9px] text-cyan-300/80 font-mono">
            LEO (&lt;2k)
          </div>
          <div className="w-[45%] bg-blue-950/50 border-r border-slate-700 flex items-center justify-center text-[9px] text-blue-300/80 font-mono">
            MEO (2k–35k)
          </div>
          <div className="w-[20%] bg-emerald-950/50 flex items-center justify-center text-[9px] text-emerald-300/80 font-mono">
            GEO (35.8k)
          </div>
          {/* Marker pin */}
          {meanAltitudeKm > 0 && (
            <div
              className="absolute top-0 bottom-0 w-1.5 bg-amber-400 shadow-glow"
              style={{
                left: `${Math.min(
                  98,
                  Math.max(
                    2,
                    meanAltitudeKm < 2000
                      ? (meanAltitudeKm / 2000) * 35
                      : meanAltitudeKm <= 35786
                      ? 35 + ((meanAltitudeKm - 2000) / (35786 - 2000)) * 45
                      : 80 + Math.min(18, ((meanAltitudeKm - 35786) / 10000) * 18),
                  ),
                )}%`,
              }}
              title={`Current mean altitude: ${Math.round(meanAltitudeKm)} km`}
            />
          )}
        </div>
        <div className="flex justify-between text-[10px] text-slate-400 font-mono">
          <span>Earth Surface (0 km)</span>
          <span>LEO Boundary (2,000 km)</span>
          <span>Geostationary Belt (35,786 km)</span>
        </div>
      </div>

      {/* Advanced Parameters Collapsible */}
      <div className="border-t border-slate-700/80 pt-3">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full flex items-center justify-between text-xs font-semibold text-cyan-400 hover:text-cyan-300 py-1.5 transition-colors focus:outline-none"
        >
          <span className="flex items-center gap-2">
            <span>⚙</span>
            <span>Advanced SGP4 Orbital Parameters (Keplerian Elements)</span>
          </span>
          <span>{showAdvanced ? 'Collapse ▲' : 'Expand Details ▼'}</span>
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 mt-3 animate-fadeIn">
            {/* RAAN */}
            <div className="bg-slate-900 border border-slate-700/80 rounded p-2.5">
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span>RAAN (Ω)</span>
                {renderParamTooltip('ra_of_asc_node')}
              </div>
              <div className="font-mono text-sm font-semibold text-slate-200">
                {data.ra_of_asc_node.toFixed(4)}°
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">Right Ascension of Ascending Node</p>
            </div>

            {/* Arg of Perigee */}
            <div className="bg-slate-900 border border-slate-700/80 rounded p-2.5">
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span>Arg of Perigee (ω)</span>
                {renderParamTooltip('arg_of_pericenter')}
              </div>
              <div className="font-mono text-sm font-semibold text-slate-200">
                {data.arg_of_pericenter.toFixed(4)}°
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">Argument of Pericenter</p>
            </div>

            {/* Mean Anomaly */}
            <div className="bg-slate-900 border border-slate-700/80 rounded p-2.5">
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span>Mean Anomaly (M)</span>
                {renderParamTooltip('mean_anomaly')}
              </div>
              <div className="font-mono text-sm font-semibold text-slate-200">
                {data.mean_anomaly.toFixed(4)}°
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">Orbital position at epoch</p>
            </div>

            {/* BSTAR */}
            <div className="bg-slate-900 border border-slate-700/80 rounded p-2.5">
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span>BSTAR Drag</span>
                {renderParamTooltip('bstar')}
              </div>
              <div className="font-mono text-sm font-semibold text-slate-200">
                {data.bstar.toExponential(4)}
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">SGP4 drag parameter (1/R_Earth)</p>
            </div>

            {/* Mean Motion Dot */}
            <div className="bg-slate-900 border border-slate-700/80 rounded p-2.5">
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span>Mean Motion Ṁ</span>
                {renderParamTooltip('mean_motion_dot')}
              </div>
              <div className="font-mono text-sm font-semibold text-slate-200">
                {data.mean_motion_dot.toExponential(4)}
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">First derivative (rev/day²)</p>
            </div>

            {/* Mean Motion DDot */}
            <div className="bg-slate-900 border border-slate-700/80 rounded p-2.5">
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span>Mean Motion M̈</span>
                {renderParamTooltip('mean_motion_ddot')}
              </div>
              <div className="font-mono text-sm font-semibold text-slate-200">
                {data.mean_motion_ddot.toExponential(4)}
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">Second derivative (rev/day³)</p>
            </div>
          </div>
        )}
      </div>

      <div className="text-[11px] text-slate-400 bg-slate-900/50 rounded p-2 border border-slate-800">
        Scientific Notice: Data sourced from CelesTrak general perturbation (GP) records.
        SGP4 propagation is analytical and subject to atmospheric modeling uncertainties.
      </div>
    </div>
  )
}
