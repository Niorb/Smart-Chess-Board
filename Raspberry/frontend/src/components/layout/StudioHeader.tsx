import React from 'react';
import { 
  User, 
  Sparkles, 
  Layers, 
  Sun, 
  Moon, 
  Palette,
  BookOpen,
  Compass,
  Play,
  GraduationCap,
  Terminal,
  Activity
} from 'lucide-react';
import { useArtisanTheme } from '../../context/ThemeContext';
import type { LichessAccount } from '../../api';
import type { StudioView } from '../../types/theme';

interface StudioHeaderProps {
  account: LichessAccount | null;
  status: string;
  isConnected: boolean;
  virtualOnly: boolean;
  onToggleVirtualOnly: () => void;
  nightMode: boolean;
  onToggleNightMode: () => void;
  opening?: { name?: string; variation?: string; eco?: string; out_of_book?: boolean } | null;
}

export const StudioHeader: React.FC<StudioHeaderProps> = ({
  account,
  status,
  isConnected,
  virtualOnly,
  onToggleVirtualOnly,
  nightMode,
  onToggleNightMode,
  opening,
}) => {
  const { currentTheme, cycleTheme, activeView, setActiveView } = useArtisanTheme();

  return (
    <header className="w-full glass-panel rounded-3xl p-3 md:p-4 mb-4 flex items-center justify-between gap-3 shrink-0">
      {/* Left: Mobile Brand & Studio State */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-2xl bg-gradient-to-tr from-amber-600 to-amber-400 p-0.5 shadow-amber-glow flex items-center justify-center text-slate-950 font-extrabold text-lg font-display lg:hidden">
            ♟
          </div>
          <div className="flex flex-col text-left">
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-sm md:text-base font-display text-white tracking-tight">
                Smart Chess
              </span>
              <span className="hidden sm:inline-block text-[9px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-bold font-mono">
                {currentTheme.label.split(' ')[0]}
              </span>
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              Status: <strong className={
                status === 'PLAYING' ? 'text-emerald-400 font-bold' :
                status === 'SEEKING' ? 'text-blue-400 font-bold animate-pulse' :
                'text-slate-300'
              }>{status}</strong>
            </span>
          </div>
        </div>

        {/* Cartographer's Path Opening Novelty Indicator */}
        {opening && opening.name && (
          <div
            title={opening.variation ? `${opening.name} (${opening.variation})` : opening.name}
            className={`hidden xl:flex items-center gap-1.5 px-3 py-1 rounded-full border text-[10px] font-bold font-mono transition-all ${
              opening.out_of_book
                ? 'bg-amber-500/15 text-amber-300 border-amber-500/35 shadow-sm'
                : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35 shadow-sm'
            }`}
          >
            <BookOpen size={12} className={opening.out_of_book ? 'text-amber-400' : 'text-emerald-400'} />
            <span className="px-1.5 py-0.2 rounded bg-slate-950 text-emerald-400 text-[9px] font-mono border border-emerald-500/20">
              {opening.eco || 'A00'}
            </span>
            <span className="max-w-[140px] truncate">{opening.name}</span>
            {opening.out_of_book && (
              <span className="px-1 rounded bg-amber-500/30 text-amber-300 text-[8px] uppercase tracking-wider font-bold">
                Novelty
              </span>
            )}
          </div>
        )}
      </div>

      {/* Center: Mobile & Tablet Quick View Switcher */}
      <div className="flex lg:hidden items-center gap-1 bg-slate-950/80 p-1 rounded-2xl border border-slate-800">
        {[
          { id: 'play', icon: <Play size={13} />, label: 'Play' },
          { id: 'analysis', icon: <Compass size={13} />, label: 'Analysis' },
          { id: 'academy', icon: <GraduationCap size={13} />, label: 'Academy' },
          { id: 'hardware', icon: <Terminal size={13} />, label: 'Board' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveView(tab.id as StudioView)}
            className={`px-2.5 py-1 rounded-xl text-[11px] font-bold font-display flex items-center gap-1 transition-all ${
              activeView === tab.id
                ? 'bg-amber-500 text-slate-950 shadow-md'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab.icon}
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Right: Lichess Account, Theme Switcher & System Telemetry */}
      <div className="flex items-center gap-2">
        {/* Lichess Account Status Pill */}
        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[11px] font-bold font-mono transition-all ${
          account?.authenticated
            ? 'bg-indigo-500/15 text-indigo-200 border-indigo-500/35 shadow-sm'
            : 'bg-slate-900 text-slate-400 border-slate-800'
        }`}>
          <User size={13} className={account?.authenticated ? 'text-indigo-400' : 'text-slate-500'} />
          <span className="hidden sm:inline">
            {account?.authenticated ? `${account.username} (${account.rating})` : 'Lichess Guest'}
          </span>
          <span className="sm:hidden font-bold">
            {account?.authenticated ? account.username : 'Guest'}
          </span>
        </div>

        {/* Theme Cycle Palette Button */}
        <button
          onClick={cycleTheme}
          title={`Active Theme: ${currentTheme.label} - Click to cycle`}
          className="p-2 rounded-2xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700 text-slate-300 hover:text-amber-400 transition-all active:scale-95 flex items-center gap-1.5"
        >
          <Palette size={15} className="text-amber-400" />
          <span className="hidden md:inline text-xs font-mono font-bold">Theme</span>
        </button>

        {/* Night / Day Mode Toggle (Mobile) */}
        <button
          onClick={onToggleNightMode}
          title={nightMode ? "Night Mode Active - Click for Day Mode" : "Day Mode Active - Click for Night Mode"}
          className="p-2 rounded-2xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700 text-slate-300 hover:text-amber-400 transition-all active:scale-95 lg:hidden"
        >
          {nightMode ? <Moon size={15} className="text-indigo-400" /> : <Sun size={15} className="text-amber-400" />}
        </button>

        {/* Server & Hardware Connection Light */}
        <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border text-[10px] font-bold font-mono ${
          isConnected ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' : 'bg-rose-500/15 text-rose-300 border-rose-500/30'
        }`}>
          <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
          <span className="hidden sm:inline">{isConnected ? 'ONLINE' : 'OFFLINE'}</span>
        </div>
      </div>
    </header>
  );
};
