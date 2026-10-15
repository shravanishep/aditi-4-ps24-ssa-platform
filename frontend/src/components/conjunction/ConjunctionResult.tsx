import type { CloseApproachResultResponse } from '../../types/api'

export default function ConjunctionResult({ data }: { data: CloseApproachResultResponse }) {
  const isCandidate = data.is_candidate_close_approach
  const missDistance = data.minimum_separation_km
  const threshold = data.threshold_km
  const relativeSpeed = data.relative_speed_km_s

  // Percentage of threshold
  const thresholdPercent = threshold > 0 ? Math.min(100, Math.round((missDistance / threshold) * 100)) : 100

  return (
    <div className="space-y-6">
      {/* Result Status Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-700/80">
        <div>
          <h4 className="text-lg font-bold text-slate-100">Encounter Evaluation Summary</h4>
          <p className="text-xs text-slate-400 mt-0.5">
            Closest approach geometry computed via analytical SGP4 propagation.
          </p>
        </div>

        <div>
          <span
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border font-semibold ${
              isCandidate
                ? 'bg-amber-950/70 text-amber-300 border-amber-700/80'
                : 'bg-emerald-950/70 text-emerald-300 border-emerald-700/80'
            }`}
          >
            <span>{isCandidate ? '⚠' : '✓'}</span>
            <span>
              {isCandidate
                ? `Close Approach Detected (< ${threshold.toFixed(1)} km)`
                : `Clear of Threshold (> ${threshold.toFixed(1)} km)`}
            </span>
          </span>
        </div>
      </div>

      {/* Evaluated Pair */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-slate-900 border border-slate-700 rounded-lg p-3.5">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block mb-1">
            Primary Object
          </span>
          <p className="text-sm font-bold text-slate-100">{data.object1_name}</p>
          <p className="text-xs font-mono text-cyan-400 mt-0.5">NORAD ID {data.object1_norad_id}</p>
        </div>

        <div className="bg-slate-900 border border-slate-700 rounded-lg p-3.5">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block mb-1">
            Secondary Object
          </span>
          <p className="text-sm font-bold text-slate-100">{data.object2_name}</p>
          <p className="text-xs font-mono text-cyan-400 mt-0.5">NORAD ID {data.object2_norad_id}</p>
        </div>
      </div>

      {/* Key Conjunction Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Miss Distance */}
        <div className="bg-slate-900 border border-slate-700 rounded-lg p-3.5">
          <div className="text-xs text-slate-400 mb-1">
            <span>Miss Distance</span>
          </div>
          <div className={`text-xl font-bold font-mono ${isCandidate ? 'text-amber-300' : 'text-emerald-400'}`}>
            {missDistance.toFixed(3)} km
          </div>
          <p className="text-[10px] text-slate-400 mt-1">
            Predicted minimum geometric separation between the two propagated objects.
          </p>
        </div>

        {/* Relative Speed */}
        <div className="bg-slate-900 border border-slate-700 rounded-lg p-3.5">
          <div className="text-xs text-slate-400 mb-1">
            <span>Relative Speed</span>
          </div>
          <div className="text-xl font-bold font-mono text-slate-100">
            {relativeSpeed.toFixed(4)} km/s
          </div>
          <p className="text-[10px] text-slate-400 mt-1">
            Relative velocity magnitude at the predicted point of closest approach.
          </p>
        </div>

        {/* Time of Closest Approach */}
        <div className="bg-slate-900 border border-slate-700 rounded-lg p-3.5">
          <div className="text-xs text-slate-400 mb-1">
            <span>Time of Closest Approach (TCA)</span>
          </div>
          <div className="text-sm font-bold font-mono text-cyan-300 truncate">
            {new Date(data.time_of_closest_approach).toISOString().replace('.000Z', 'Z')}
          </div>
          <p className="text-[10px] text-slate-400 mt-1">
            UTC epoch when the minimum separation distance is predicted.
          </p>
        </div>
      </div>

      {/* Visual Relative Separation Proximity Bar */}
      <div className="bg-slate-900/70 border border-slate-700/80 rounded-lg p-3.5 space-y-2">
        <div className="flex justify-between items-center text-xs">
          <span className="font-semibold text-slate-300">Separation Proximity Gauge</span>
          <span className="text-slate-400 font-mono text-[11px]">
            {missDistance.toFixed(2)} km / {threshold.toFixed(2)} km threshold
          </span>
        </div>
        <div className="w-full bg-slate-800 rounded-full h-3 overflow-hidden relative border border-slate-700">
          <div
            className={`h-full transition-all duration-500 ${
              isCandidate ? 'bg-amber-500' : 'bg-emerald-500'
            }`}
            style={{ width: `${thresholdPercent}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-slate-400 font-mono">
          <span>0 km (Theoretical Collision)</span>
          <span>Threshold ({threshold.toFixed(0)} km)</span>
        </div>
      </div>

      {/* Evaluation Window Details */}
      <div className="grid grid-cols-2 gap-3 text-xs bg-slate-900/50 p-3 rounded border border-slate-800 font-mono text-slate-300">
        <div>
          <span className="text-[10px] text-slate-400 block font-sans">Window Start</span>
          <span>{new Date(data.analysis_start_time).toISOString()}</span>
        </div>
        <div>
          <span className="text-[10px] text-slate-400 block font-sans">Window End</span>
          <span>{new Date(data.analysis_end_time).toISOString()}</span>
        </div>
      </div>

      {/* Propagation Notes if any */}
      {data.error_message && (
        <div className="rounded-md bg-amber-950/40 border border-amber-800/60 p-3 text-amber-300 text-xs">
          <span className="font-semibold">Propagation Notice: </span>
          {data.error_message}
        </div>
      )}

      {/* Informational limitation note */}
      <div className="text-[11px] text-slate-400 pt-2 border-t border-slate-800">
        <p>
          Research prototype using public orbital data. Results are advisory and are not operational collision-avoidance guidance. Miss distance represents analytical orbital geometry, NOT physical collision probability.
        </p>
      </div>
    </div>
  )
}
