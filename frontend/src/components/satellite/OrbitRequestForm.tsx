import { useState } from 'react'

interface Props {
  onPropagate: (timestamp: string) => void
  loading: boolean
}

export default function OrbitRequestForm({ onPropagate, loading }: Props) {
  const [datetime, setDatetime] = useState('')
  const [validationError, setValidationError] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!datetime) {
      setValidationError('Please select a date and time.')
      return
    }
    setValidationError('')
    // datetime-local gives "YYYY-MM-DDTHH:mm"; append ":00Z" for UTC ISO-8601.
    const timestamp = `${datetime}:00Z`
    onPropagate(timestamp)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <label className="block text-sm text-slate-300 font-medium">
        Propagation Time
      </label>
      <div className="flex gap-2 flex-wrap items-start">
        <div>
          <input
            type="datetime-local"
            value={datetime}
            onChange={e => {
              setDatetime(e.target.value)
              setValidationError('')
            }}
            className="px-3 py-2 rounded-md bg-slate-700 border border-slate-600 text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-600 focus:border-transparent text-sm"
          />
          <p className="text-xs text-slate-500 mt-1">Input interpreted as UTC.</p>
        </div>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium transition-colors"
        >
          {loading ? 'Propagating…' : 'Propagate'}
        </button>
      </div>
      {validationError && (
        <p className="text-red-400 text-xs">{validationError}</p>
      )}
    </form>
  )
}
