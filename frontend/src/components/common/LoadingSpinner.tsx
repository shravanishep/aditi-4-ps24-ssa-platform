type Size = 'sm' | 'md' | 'lg'

const sizes: Record<Size, string> = {
  sm: 'h-4 w-4 border-2',
  md: 'h-8 w-8 border-2',
  lg: 'h-12 w-12 border-4',
}

export default function LoadingSpinner({ size = 'md' }: { size?: Size }) {
  return (
    <div
      className={`animate-spin rounded-full border-slate-600 border-t-cyan-400 ${sizes[size]}`}
    />
  )
}
