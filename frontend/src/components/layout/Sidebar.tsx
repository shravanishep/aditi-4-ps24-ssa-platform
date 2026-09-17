import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard', icon: '▦' },
  { to: '/satellites', label: 'Satellite Explorer', icon: '◎' },
  { to: '/conjunction', label: 'Conjunction Analysis', icon: '⊕' },
]

export default function Sidebar() {
  return (
    <nav className="w-56 shrink-0 min-h-screen bg-slate-900 border-r border-slate-700 flex flex-col">
      {/* Brand */}
      <div className="px-4 py-5 border-b border-slate-700">
        <p className="text-xs text-slate-500 font-medium tracking-widest uppercase">
          ADITI 4.0
        </p>
        <p className="text-slate-100 font-semibold text-sm mt-0.5">SSA Platform</p>
      </div>

      {/* Nav links */}
      <div className="flex-1 px-2 py-4 space-y-0.5">
        {navItems.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive
                  ? 'bg-cyan-900 text-cyan-300 font-medium'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`
            }
          >
            <span className="text-base leading-none">{icon}</span>
            {label}
          </NavLink>
        ))}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-700">
        <p className="text-xs text-slate-600">Layer 5 · Dashboard</p>
      </div>
    </nav>
  )
}
