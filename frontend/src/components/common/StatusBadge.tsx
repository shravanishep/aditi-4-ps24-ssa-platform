type Status = 'ok' | 'error' | 'loading' | 'unknown'

const config: Record<Status, { label: string; classes: string }> = {
  ok: {
    label: 'Online',
    classes: 'bg-green-900 text-green-400 border-green-700',
  },
  error: {
    label: 'Offline',
    classes: 'bg-red-900 text-red-400 border-red-700',
  },
  loading: {
    label: 'Checking…',
    classes: 'bg-slate-700 text-slate-400 border-slate-600',
  },
  unknown: {
    label: 'Unknown',
    classes: 'bg-yellow-900 text-yellow-400 border-yellow-700',
  },
}

export default function StatusBadge({ status }: { status: Status }) {
  const { label, classes } = config[status]
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${classes}`}
    >
      {label}
    </span>
  )
}
