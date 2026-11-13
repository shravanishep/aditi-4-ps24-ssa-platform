import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/satellites', label: 'Satellite Explorer', icon: '🛰️' },
  { to: '/conjunction', label: 'Conjunction & CAM', icon: '⚡' },
  { to: '/pc-analysis', label: 'Collision Probability', icon: '⊗' },
  { to: '/events', label: 'Event Timeline', icon: '📜' },
  { to: '/globe', label: '3D Globe', icon: '🌐' },
]

export default function Sidebar() {
  return (
    <nav className="w-60 shrink-0 min-h-screen bg-slate-900 border-r border-slate-700/80 flex flex-col select-none">
      {/* Brand Header */}
      <div className="px-5 py-5 border-b border-slate-800">
        <p className="text-[11px] text-sky-400 font-semibold tracking-wider uppercase font-mono">
          ADITI 4.0 · PS24
        </p>
        <p className="text-slate-100 font-bold text-base mt-0.5 tracking-tight">
          SSA Research Platform
        </p>
        <p className="text-[11px] text-slate-500 mt-0.5">
          Orbital Surveillance & Analysis
        </p>
      </div>

      {/* Navigation Links */}
      <div className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                isActive
                  ? 'bg-slate-800 text-sky-300 border border-slate-700/80 shadow-xs'
                  : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 border border-transparent'
              }`
            }
          >
            <span className="text-sm leading-none opacity-80">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </div>

      {/* Footer Info */}
      <div className="px-4 py-3 border-t border-slate-800/80 text-[11px] text-slate-500 space-y-0.5">
        <div className="flex items-center justify-between">
          <span className="font-mono text-slate-400">v0.5.0</span>
          <span className="text-emerald-500 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block"></span>
            Operational
          </span>
        </div>
        <p className="text-[10px] text-slate-600 truncate">
          Academic Research Prototype
        </p>
      </div>
    </nav>
  )
}
