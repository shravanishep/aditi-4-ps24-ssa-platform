interface Props {
  label: string
  value: string | number | null | undefined
  mono?: boolean
}

export default function InfoCard({ label, value, mono = false }: Props) {
  return (
    <div className="bg-slate-900 rounded-md border border-slate-700 p-3">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-slate-100 text-sm break-all ${mono ? 'font-mono' : ''}`}>
        {value ?? '—'}
      </p>
    </div>
  )
}
