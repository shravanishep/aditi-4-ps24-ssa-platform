import { useState } from 'react'
import type { ConjunctionAnalysisRequest } from '../../types/api'

interface Props {
  onSubmit: (req: ConjunctionAnalysisRequest) => void
  loading: boolean
}

export default function ConjunctionForm({ onSubmit, loading }: Props) {
  const [norad1, setNorad1] = useState('')
  const [norad2, setNorad2] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [threshold, setThreshold] = useState('100')
  const [coarseStep, setCoarseStep] = useState('60')
  const [fineStep, setFineStep] = useState('1')
  const [errors, setErrors] = useState<Record<string, string>>({})

  function validate(): boolean {
    const e: Record<string, string> = {}
    const n1 = parseInt(norad1.trim(), 10)
    const n2 = parseInt(norad2.trim(), 10)

    if (!norad1.trim() || isNaN(n1) || n1 <= 0) e.norad1 = 'Valid NORAD ID required.'
    if (!norad2.trim() || isNaN(n2) || n2 <= 0) e.norad2 = 'Valid NORAD ID required.'
    if (n1 > 0 && n2 > 0 && n1 === n2) e.norad2 = 'NORAD IDs must be different.'
    if (!startTime) e.startTime = 'Start time required.'
    if (!endTime) e.endTime = 'End time required.'
    if (startTime && endTime && endTime <= startTime)
      e.endTime = 'End time must be after start time.'

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
      start_time: `${startTime}:00Z`,
      end_time: `${endTime}:00Z`,
      threshold_km: parseFloat(threshold),
      coarse_step_sec: parseFloat(coarseStep) || 60,
      fine_step_sec: parseFloat(fineStep) || 1,
    })
  }

  const inputCls =
    'w-full px-3 py-2 rounded-md bg-slate-700 border border-slate-600 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-600 focus:border-transparent text-sm'

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* NORAD IDs */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-slate-300 font-medium mb-1">NORAD ID 1</label>
          <input
            type="number" min="1" value={norad1}
            onChange={e => setNorad1(e.target.value)}
            placeholder="e.g. 25544" className={inputCls}
          />
          {errors.norad1 && <p className="text-red-400 text-xs mt-1">{errors.norad1}</p>}
        </div>
        <div>
          <label className="block text-sm text-slate-300 font-medium mb-1">NORAD ID 2</label>
          <input
            type="number" min="1" value={norad2}
            onChange={e => setNorad2(e.target.value)}
            placeholder="e.g. 20580" className={inputCls}
          />
          {errors.norad2 && <p className="text-red-400 text-xs mt-1">{errors.norad2}</p>}
        </div>
      </div>

      {/* Time window */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-slate-300 font-medium mb-1">Start Time (UTC)</label>
          <input
            type="datetime-local" value={startTime}
            onChange={e => setStartTime(e.target.value)} className={inputCls}
          />
          {errors.startTime && <p className="text-red-400 text-xs mt-1">{errors.startTime}</p>}
        </div>
        <div>
          <label className="block text-sm text-slate-300 font-medium mb-1">End Time (UTC)</label>
          <input
            type="datetime-local" value={endTime}
            onChange={e => setEndTime(e.target.value)} className={inputCls}
          />
          {errors.endTime && <p className="text-red-400 text-xs mt-1">{errors.endTime}</p>}
        </div>
      </div>

      {/* Analysis parameters */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-sm text-slate-300 font-medium mb-1">
            Threshold (km)
          </label>
          <input
            type="number" min="0.001" step="any" value={threshold}
            onChange={e => setThreshold(e.target.value)} className={inputCls}
          />
          {errors.threshold && <p className="text-red-400 text-xs mt-1">{errors.threshold}</p>}
        </div>
        <div>
          <label className="block text-sm text-slate-300 font-medium mb-1">
            Coarse Step (s)
          </label>
          <input
            type="number" min="1" step="any" value={coarseStep}
            onChange={e => setCoarseStep(e.target.value)} className={inputCls}
          />
        </div>
        <div>
          <label className="block text-sm text-slate-300 font-medium mb-1">
            Fine Step (s)
          </label>
          <input
            type="number" min="0.1" step="any" value={fineStep}
            onChange={e => setFineStep(e.target.value)} className={inputCls}
          />
        </div>
      </div>

      <p className="text-xs text-slate-500">
        Time inputs are treated as UTC. Analysis may take several seconds.
      </p>

      <button
        type="submit"
        disabled={loading}
        className="w-full py-2.5 bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium transition-colors"
      >
        {loading ? 'Analyzing…' : 'Analyze'}
      </button>
    </form>
  )
}
