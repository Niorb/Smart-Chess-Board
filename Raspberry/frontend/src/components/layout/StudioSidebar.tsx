import React from 'react';
import { 
  Play, 
  Compass, 
  GraduationCap, 
  Terminal, 
  Layers, 
  Sparkles,
  Sun,
  Moon,
  Radio
} from 'lucide-react';
import { useArtisanTheme } from '../../context/useArtisanTheme';
import type { StudioView } from '../../types/theme';

interface StudioSidebarProps {
  status: string;
  isConnected: boolean;
  virtualOnly: boolean;
  onToggleVirtualOnly: () => void;
  nightMode: boolean;
  onToggleNightMode: () => void;
  hasActiveGesture?: boolean;
}

export const StudioSidebar: React.FC<StudioSidebarProps> = ({
  status,
  isConnected,
  virtualOnly,
  onToggleVirtualOnly,
  nightMode,
  onToggleNightMode,
  hasActiveGesture,
}) => {
  const { activeView, setActiveView, lens, toggleLens } = useArtisanTheme();

  const navItems: Array<{ id: StudioView; label: string; sub: string; icon: React.ReactNode; badge?: string }> = [
    {
      id: 'play',
      label: 'Play Studio',
      sub: 'Lichess & Stockfish Matchmaking',
      icon: <Play size={18} />,
      badge: status === 'PLAYING' ? 'LIVE' : status === 'SEEKING' ? 'SEEKING' : undefined,
    },
    {
      id: 'analysis',
      label: 'Grandmaster Analysis',
      sub: 'The Grandmaster\'s Lens & Multi-PV',
      icon: <Compass size={18} />,
      badge: status === 'ANALYSIS' ? 'ACTIVE' : undefined,
    },
    {
      id: 'academy',
      label: 'Academy & Drills',
      sub: 'GM Classics, Blunders & Endgames',
      icon: <GraduationCap size={18} />,
    },
    {
      id: 'hardware',
      label: 'Hardware Workshop',
      sub: 'ADC Sensor Matrix & LED Controls',
      icon: <Terminal size={18} />,
    },
  ];

  return (
    <aside className="w-64 glass-panel rounded-3xl p-4 flex flex-col justify-between shrink-0 hidden lg:flex">
      {/* Brand & Studio Thesis */}
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-3 px-2">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-amber-600 to-amber-400 p-0.5 shadow-amber-glow flex items-center justify-center text-slate-950 font-extrabold text-xl font-display">
            ♟
          </div>
          <div className="flex flex-col text-left">
            <h1 className="text-base font-extrabold font-display tracking-tight text-white flex items-center gap-1.5">
              Smart Chess
              <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-amber-400/20 text-amber-300 border border-amber-400/40">
                PRO
              </span>
            </h1>
            <span className="text-[11px] text-slate-400 font-mono">Nordic Artisan Studio</span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex flex-col gap-1.5">
          {navItems.map((item) => {
            const isActive = activeView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveView(item.id)}
                className={`flex items-center justify-between p-3 rounded-2xl transition-all duration-200 text-left ${
                  isActive
                    ? 'bg-gradient-to-r from-amber-500/25 to-amber-600/10 border border-amber-500/40 text-white shadow-md'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-xl transition-colors ${
                    isActive ? 'bg-amber-500 text-slate-950' : 'bg-slate-800 text-slate-400'
                  }`}>
                    {item.icon}
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs font-bold font-display">{item.label}</span>
                    <span className="text-[10px] opacity-70 font-sans leading-tight truncate max-w-[110px]">
                      {item.sub}
                    </span>
                  </div>
                </div>

                {item.badge && (
                  <span className={`text-[9px] font-mono font-extrabold px-1.5 py-0.5 rounded-full ${
                    item.badge === 'LIVE' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 animate-pulse' :
                    item.badge === 'SEEKING' ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 animate-pulse' :
                    'bg-violet-500/20 text-violet-300 border border-violet-500/40'
                  }`}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Signature Lens Controls */}
        <div className="flex flex-col gap-2.5 p-3 rounded-2xl bg-slate-900/60 border border-slate-800/80">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono flex items-center gap-1.5">
            <Sparkles size={12} className="text-amber-400" />
            Digital Twin Lens
          </span>
          <div className="grid grid-cols-2 gap-1.5">
            <button
              onClick={() => toggleLens('aura')}
              className={`p-2 text-[10px] font-mono font-bold rounded-xl border transition-all ${
                lens.aura
                  ? 'bg-amber-500/20 border-amber-500/40 text-amber-300 shadow-sm'
                  : 'bg-slate-950/60 border-slate-800 text-slate-500 hover:text-slate-300'
              }`}
            >
              Magnetic Aura
            </button>
            <button
              onClick={() => toggleLens('ledBezel')}
              className={`p-2 text-[10px] font-mono font-bold rounded-xl border transition-all ${
                lens.ledBezel
                  ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300 shadow-sm'
                  : 'bg-slate-950/60 border-slate-800 text-slate-500 hover:text-slate-300'
              }`}
            >
              LED Bezel
            </button>
            <button
              onClick={() => toggleLens('evalBar')}
              className={`p-2 text-[10px] font-mono font-bold rounded-xl border transition-all ${
                lens.evalBar
                  ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300 shadow-sm'
                  : 'bg-slate-950/60 border-slate-800 text-slate-500 hover:text-slate-300'
              }`}
            >
              Eval Meter
            </button>
            <button
              onClick={() => toggleLens('hints')}
              className={`p-2 text-[10px] font-mono font-bold rounded-xl border transition-all ${
                lens.hints
                  ? 'bg-violet-500/20 border-violet-500/40 text-violet-300 shadow-sm'
                  : 'bg-slate-950/60 border-slate-800 text-slate-500 hover:text-slate-300'
              }`}
            >
              Hints / PV
            </button>
          </div>
        </div>
      </div>

      {/* Hardware Link, Gesture, and Night Mode Badges */}
      <div className="flex flex-col gap-2 pt-4 border-t border-slate-800/80">
        {/* Physical Gesture Status */}
        {hasActiveGesture && (
          <div className="bg-gradient-to-r from-cyan-500/20 to-amber-500/20 border border-cyan-400/40 rounded-xl p-2 flex items-center gap-2 animate-pulse">
            <Radio size={14} className="text-cyan-300 animate-spin" />
            <span className="text-[10px] font-bold text-cyan-200">Gesture Menu Active</span>
          </div>
        )}

        {/* Quick Toggles */}
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={onToggleVirtualOnly}
            title={virtualOnly ? "Switch to Physical Hardware Board" : "Switch to Virtual Only Mode"}
            className={`p-2 rounded-xl border flex items-center justify-center gap-1.5 text-[10px] font-mono font-bold transition-all ${
              virtualOnly
                ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:border-emerald-400'
            }`}
          >
            <Layers size={13} />
            <span>{virtualOnly ? 'Virtual' : 'Hardware'}</span>
          </button>

          <button
            onClick={onToggleNightMode}
            title={nightMode ? "Night Mode Active (Warm Ambient Backlight)" : "Day Mode Active"}
            className={`p-2 rounded-xl border flex items-center justify-center gap-1.5 text-[10px] font-mono font-bold transition-all ${
              nightMode
                ? 'bg-indigo-950/90 text-indigo-300 border-indigo-500/50 shadow-sm'
                : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
            }`}
          >
            {nightMode ? <Moon size={13} className="text-indigo-400" /> : <Sun size={13} className="text-amber-400" />}
            <span>{nightMode ? 'Night' : 'Day'}</span>
          </button>
        </div>

        {/* Link Status Pill */}
        <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
            <span className="text-[11px] font-mono text-slate-300">
              {isConnected ? 'ESP32 Online' : 'Link Offline'}
            </span>
          </div>
          <span className="text-[10px] font-mono text-slate-500 font-bold uppercase">
            {status}
          </span>
        </div>
      </div>
    </aside>
  );
};
