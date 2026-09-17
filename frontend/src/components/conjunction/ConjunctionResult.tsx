import type { CloseApproachResultResponse } from '../../types/api'
import InfoCard from '../common/InfoCard'

export default function ConjunctionResult({ data }: { data: CloseApproachResultResponse }) {
  const isCandidate = data.is_candidate_close_approach

  return (
    <div className="space-y-4">
      {/* Header with candidate flag */}
      <div className="flex items-center gap-3 flex-wrap">
        <h4 className="text-slate-200 font-medium">Analysis Result</h4>
        <span
          className={`text-xs px-2.5 py-0.5 rounded-full border font-semibold ${
            isCandidate
              ? 'bg-amber-900 text-amber-300 border-amber-700'
              : 'bg-slate-700 text-slate-400 border-slate-600'
          }`}
        >
          {isCandidate ? '⚠ Candidate Close Approach' : '✓ No Close Approach Detected'}
        </span>
      </div>

      {/* Object names */}
      <div className="grid grid-cols-2 gap-3">
        <InfoCard
          label={`Object 1 · NORAD ${data.object1_norad_id}`}
          value={data.object1_name}
        />
        <InfoCard
          label={`Object 2 · NORAD ${data.object2_norad_id}`}
          value={data.object2_name}
        />
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <InfoCard
          label="Time of Closest Approach"
          value={new Date(data.time_of_closest_approach).toISOString()}
          mono
        />
        <InfoCard
          label="Minimum Separation (km)"
          value={data.minimum_separation_km.toFixed(3)}
          mono
        />
        <InfoCard
          label="Relative Speed (km/s)"
          value={data.relative_speed_km_s.toFixed(4)}
          mono
        />
        <InfoCard
          label="Threshold (km)"
          value={data.threshold_km.toFixed(3)}
          mono
        />
        <InfoCard
          label="Analysis Start"
          value={new Date(data.analysis_start_time).toISOString()}
          mono
        />
        <InfoCard
          label="Analysis End"
          value={new Date(data.analysis_end_time).toISOString()}
          mono
        />
      </div>

      {/* Propagation notes (non-fatal warnings from the backend) */}
      {data.error_message && (
        <div className="rounded-md bg-yellow-950 border border-yellow-800 p-3 text-yellow-300 text-xs">
          <span className="font-semibold">Propagation notes: </span>
          {data.error_message}
        </div>
      )}

      <p className="text-xs text-slate-600">
        Analytical prototype based on SGP4 propagation and public orbital data.
        Not a collision probability or operational collision-avoidance output.
      </p>
    </div>
  )
}
