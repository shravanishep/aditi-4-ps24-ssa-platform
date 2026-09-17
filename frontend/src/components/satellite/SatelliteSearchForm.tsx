import { useState } from 'react'

interface Props {
  onSearch: (noradId: number) => void
  loading: boolean
}

export default function SatelliteSearchForm({ onSearch, loading }: Props) {
  const [input, setInput] = useState('')
  const [validationError, setValidationError] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const id = parseInt(input.trim(), 10)
    if (!input.trim() || isNaN(id) || id <= 0) {
      setValidationError('Enter a valid positive integer NORAD catalog ID.')
      return
    }
    setValidationError('')
    onSearch(id)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <label className="block text-sm text-slate-300 font-medium">
        NORAD Catalog ID
      </label>
      <div className="flex gap-2 flex-wrap">
        <input
          type="number"
          min="1"
          value={input}
          onChange={e => {
            setInput(e.target.value)
            setValidationError('')
          }}
          placeholder="e.g. 25544"
          className="w-48 px-3 py-2 rounded-md bg-slate-700 border border-slate-600 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-600 focus:border-transparent text-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium transition-colors"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </div>
      {validationError && (
        <p className="text-red-400 text-xs">{validationError}</p>
      )}
    </form>
  )
}
