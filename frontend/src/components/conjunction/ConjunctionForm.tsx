import { useState } from 'react'
import type { ConjunctionAnalysisRequest } from '../../types/api'

interface Props {
  onSubmit: (req: ConjunctionAnalysisRequest) => void
  loading: boolean
}

export default function ConjunctionForm({ onSubmit, loading }: Props) {
  const [norad1, setNorad1] = useState('25544') // ISS default
  const [norad2, setNorad2] = useState('20580') // Hubble default
  const [startTime, setStartTime] = useState(() => {
    const d = new Date()
    return d.toISOString().slice(0, 16)
  })
  const [endTime, setEndTime] = useState(() => {
    const d = new Date(Date.now() + 24 * 3600 * 1000)
    return d.toISOString().slice(0, 16)
  })
  const [threshold, setThreshold] = useState('100')
  const [coarseStep, setCoarseStep] = useState('60')
  const [fineStep, setFineStep] = useState('1')
  const [errors, setErrors] = useState<Record<string, string>>({})

  function validate(): boolean {
    const e: Record<string, string> = {}
    const n1 = parseInt(norad1.trim(), 10)
    const n2 = parseInt(norad2.trim(), 10)

    if (!norad1.trim() || isNaN(n1) || n1 <= 0) e.norad1 = 'Valid positive NORAD ID required.'
    if (!norad2.trim() || isNaN(n2) || n2 <= 0) e.norad2 = 'Valid positive NORAD ID required.'
    if (n1 > 0 && n2 > 0 && n1 === n2) e.norad2 = 'NORAD IDs must be distinct objects.'
    if (!startTime) e.startTime = 'Start time required.'
    if (!endTime) e.endTime = 'End time required.'
    if (startTime && endTime && endTime <= startTime)
      e.endTime = 'End time must be later than start time.'

    const thr = parseFloat(threshold)
    if (isNaN(thr) || thr <= 0) e.threshold = 'Threshold must be greater than 0.'

    setErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    onSubmit({
      norad1: parseInt(norad1.trim(), 10),
      norad2: parseInt(norad2.trim(), 10),
      start_time: startTime.endsWith('Z') ? startTime : `${startTime}:00Z`,
      end_time: endTime.endsWith('Z') ? endTime : `${endTime}:00Z`,
      threshold_km: parseFloat(threshold),
      coarse_step_sec: parseFloat(coarseStep) || 60,
      fine_step_sec: parseFloat(fineStep) || 1,
    })
  }

  const inputCls =
    'w-full px-3 py-2 rounded-md bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-600 focus:border-transparent text-sm font-mono'

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* NORAD Objects Selection */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          Target Orbital Pair
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-300 font-medium mb-1">
              Primary Object NORAD ID
            </label>
            <input
              type="number"
              min="1"
              value={norad1}
              onChange={(e) => setNorad1(e.target.value)}
              placeholder="e.g. 25544 (ISS)"
              className={inputCls}
            />
            <p className="text-[11px] text-slate-400 mt-1">Target object to evaluate.</p>
            {errors.norad1 && <p className="text-rose-400 text-xs mt-1">{errors.norad1}</p>}
          </div>

          <div>
            <label className="block text-xs text-slate-300 font-medium mb-1">
              Secondary Object NORAD ID
            </label>
            <input
              type="number"
              min="1"
              value={norad2}
              onChange={(e) => setNorad2(e.target.value)}
              placeholder="e.g. 20580 (Hubble)"
              className={inputCls}
            />
            <p className="text-[11px] text-slate-400 mt-1">Conjunction candidate object.</p>
            {errors.norad2 && <p className="text-rose-400 text-xs mt-1">{errors.norad2}</p>}
          </div>
        </div>
      </div>

      {/* Propagation Search Window */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          Evaluation Search Window (UTC)
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-300 font-medium mb-1">
              Window Start (UTC)
            </label>
            <input
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className={inputCls}
            />
            {errors.startTime && <p className="text-rose-400 text-xs mt-1">{errors.startTime}</p>}
          </div>
          <div>
            <label className="block text-xs text-slate-300 font-medium mb-1">
              Window End (UTC)
            </label>
            <input
              type="datetime-local"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              className={inputCls}
            />
            {errors.endTime && <p className="text-rose-400 text-xs mt-1">{errors.endTime}</p>}
          </div>
        </div>
      </div>

      {/* Analysis Tuning Parameters */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          Search Resolution & Thresholds
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs text-slate-300 font-medium mb-1">
              Miss Distance Threshold (km)
            </label>
            <input
              type="number"
              min="0.1"
              step="any"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              className={inputCls}
            />
            <p className="text-[10px] text-slate-400 mt-1">
              Maximum separation distance to flag as a close approach encounter.
            </p>
            {errors.threshold && <p className="text-rose-400 text-xs mt-1">{errors.threshold}</p>}
          </div>

          <div>
            <label className="block text-xs text-slate-300 font-medium mb-1">
              Coarse Step (s)
            </label>
            <input
              type="number"
              min="10"
              step="any"
              value={coarseStep}
              onChange={(e) => setCoarseStep(e.target.value)}
              className={inputCls}
            />
            <p className="text-[10px] text-slate-400 mt-1">
              Initial coarse propagation interval across the search window.
            </p>
          </div>

          <div>
            <label className="block text-xs text-slate-300 font-medium mb-1">
              Fine Step (s)
            </label>
            <input
              type="number"
              min="0.1"
              step="any"
              value={fineStep}
              onChange={(e) => setFineStep(e.target.value)}
              className={inputCls}
            />
            <p className="text-[10px] text-slate-400 mt-1">
              Interpolation step to refine minimum separation at TCA.
            </p>
          </div>
        </div>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="w-full py-2.5 bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-700 text-white rounded-md text-sm font-semibold transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed shadow-md"
      >
        <span>{loading ? 'Evaluating Orbital Conjunction…' : 'Run Conjunction Analysis'}</span>
      </button>
    </form>
  )
}
