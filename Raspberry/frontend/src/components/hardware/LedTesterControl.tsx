import React, { useState } from 'react';
import { Sparkles, PowerOff, Play, Wand2 } from 'lucide-react';

interface LedTesterControlProps {
  onTestLeds: () => void;
  onClearLeds: () => void;
  onTriggerAnimation: (name: string, params?: Record<string, unknown>) => void;
  onTestTrace: (uci: string, isCapture?: boolean) => void;
}

const PRESET_ANIMATIONS = [
  { id: 'GAME_STARTED', label: 'Game Start Fanfare', color: 'border-emerald-500/40 text-emerald-300' },
  { id: 'GAME_WON', label: 'Victory Cascade', color: 'border-amber-500/40 text-amber-300' },
  { id: 'GAME_LOST', label: 'Eclipse Defeat', color: 'border-rose-500/40 text-rose-300' },
  { id: 'GAME_DRAWN', label: 'Equilibrium Draw', color: 'border-cyan-500/40 text-cyan-300' },
  { id: 'BOARD_READY', label: 'Board Ready Ambient', color: 'border-indigo-500/40 text-indigo-300' },
  { id: 'SEEKING', label: 'Matchmaking Pulse', color: 'border-purple-500/40 text-purple-300' },
];

export const LedTesterControl: React.FC<LedTesterControlProps> = ({
  onTestLeds,
  onClearLeds,
  onTriggerAnimation,
  onTestTrace,
}) => {
  const [traceUci, setTraceUci] = useState('e2e4');

  return (
    <div className="glass-panel rounded-3xl p-5 flex flex-col gap-4 text-left shadow-artisan">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
            <Sparkles size={18} />
          </div>
          <div>
            <h3 className="text-sm font-bold font-display text-white">WS2812B LED Light Array Test Bench</h3>
            <p className="text-[11px] text-slate-400 font-sans">Trigger lighting sequences and verify dual strip rendering</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onTestLeds}
            className="px-3 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-display font-bold text-xs shadow-cyan-glow transition-all"
          >
            RGB Full Test
          </button>
          <button
            onClick={onClearLeds}
            className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 font-display font-bold text-xs transition-all flex items-center gap-1"
          >
            <PowerOff size={13} />
            <span>Clear</span>
          </button>
        </div>
      </div>

      {/* Preset Animation Triggers */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
          Preset Light Animations
        </span>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {PRESET_ANIMATIONS.map((anim) => (
            <button
              key={anim.id}
              onClick={() => onTriggerAnimation(anim.id)}
              className={`p-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800/80 border text-xs font-display font-bold transition-all hover:scale-105 active:scale-95 flex items-center justify-between ${anim.color}`}
            >
              <span>{anim.label}</span>
              <Wand2 size={13} />
            </button>
          ))}
        </div>
      </div>

      {/* Test Trace Move */}
      <div className="flex flex-col gap-1.5 pt-2 border-t border-slate-800">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
          Test Move Trace Illumination
        </span>
        <div className="flex gap-2">
          <input
            type="text"
            value={traceUci}
            onChange={(e) => setTraceUci(e.target.value)}
            placeholder="e.g. e2e4"
            className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-white"
          />
          <button
            onClick={() => onTestTrace(traceUci, false)}
            className="px-3 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-display font-bold text-xs shadow flex items-center gap-1 transition-all"
          >
            <Play size={13} />
            <span>Trace Move</span>
          </button>
          <button
            onClick={() => onTestTrace(traceUci, true)}
            className="px-3 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-display font-bold text-xs shadow-rose-glow flex items-center gap-1 transition-all"
          >
            <span>Capture Trace</span>
          </button>
        </div>
      </div>
    </div>
  );
};
