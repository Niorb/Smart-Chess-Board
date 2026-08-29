import React, { useState } from 'react';
import { Ban, RotateCcw, Activity } from 'lucide-react';

interface AdcSensorMatrixProps {
  adcGrid?: number[][];
  baselines?: number[][];
  disabledSquares?: number[][];
  positiveThresh: number;
  negativeThresh: number;
  onCalibrateSquare: (col: number, row: number) => void;
  onToggleDisableSquare: (col: number, row: number) => void;
}

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

export const AdcSensorMatrix: React.FC<AdcSensorMatrixProps> = ({
  adcGrid = [],
  baselines = [],
  disabledSquares = [],
  positiveThresh,
  negativeThresh,
  onCalibrateSquare,
  onToggleDisableSquare,
}) => {
  const [inspectSquare, setInspectSquare] = useState<[number, number] | null>(null);

  const disabledSet = new Set(disabledSquares.map(([c, r]) => `${c},${r}`));

  return (
    <div className="glass-panel rounded-3xl p-5 flex flex-col gap-4 text-left shadow-artisan">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-amber-500/20 text-amber-300 border border-amber-500/40">
            <Activity size={18} />
          </div>
          <div>
            <h3 className="text-sm font-bold font-display text-white">8×8 Hall Sensor Matrix Telemetry</h3>
            <p className="text-[11px] text-slate-400 font-sans">Live ADC readings vs baseline magnetic offsets</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400" /> +{positiveThresh}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-cyan-400" /> -{negativeThresh}
          </span>
        </div>
      </div>

      {/* 8x8 Sensor Matrix Grid */}
      <div
        className="grid grid-cols-8 gap-1 p-2 rounded-2xl bg-slate-950 border border-slate-800"
        style={{ aspectRatio: '1 / 1' }}
      >
        {Array.from({ length: 64 }).map((_, idx) => {
          const rowFromTop = Math.floor(idx / 8);
          const col = idx % 8;
          const row = 7 - rowFromTop;
          const raw = adcGrid[col]?.[row] ?? 0;
          const base = baselines[col]?.[row] ?? 0;
          const delta = raw - base;
          const isPos = delta >= positiveThresh;
          const isNeg = delta <= -negativeThresh;
          const isDisabled = disabledSet.has(`${col},${row}`);
          const sqName = `${FILES[col]}${row + 1}`;

          let cellBg = 'bg-slate-900/60 border-slate-800 text-slate-400';
          if (isDisabled) {
            cellBg = 'bg-slate-950 border-rose-900/40 text-slate-600';
          } else if (isPos) {
            cellBg = 'bg-emerald-500/30 border-emerald-400 text-emerald-200 shadow-emerald-glow';
          } else if (isNeg) {
            cellBg = 'bg-cyan-500/30 border-cyan-400 text-cyan-200 shadow-cyan-glow';
          }

          return (
            <button
              key={`${col}-${row}`}
              onClick={() => setInspectSquare([col, row])}
              className={`relative rounded-xl border flex flex-col items-center justify-center p-1 transition-all hover:scale-105 active:scale-95 ${cellBg}`}
              title={`Square ${sqName} | ADC: ${raw} | Base: ${base} | Delta: ${delta > 0 ? '+' : ''}${delta}`}
            >
              <span className="text-[9px] font-mono font-bold">{sqName}</span>
              <span className="text-[10px] font-mono font-extrabold">{raw}</span>
              <span className="text-[8px] font-mono opacity-70">
                {delta > 0 ? `+${delta}` : delta}
              </span>
            </button>
          );
        })}
      </div>

      {/* Per-Square Inspector & Actions */}
      {inspectSquare && (
        <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 flex items-center justify-between animate-fadeIn">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/20 border border-amber-400 text-amber-300 font-mono font-bold text-sm">
              {FILES[inspectSquare[0]]}{inspectSquare[1] + 1}
            </div>
            <div className="flex flex-col text-left">
              <span className="text-xs font-bold font-display text-white">
                ADC: {adcGrid[inspectSquare[0]]?.[inspectSquare[1]] ?? 0} • Base: {baselines[inspectSquare[0]]?.[inspectSquare[1]] ?? 0}
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                Status: {disabledSet.has(`${inspectSquare[0]},${inspectSquare[1]}`) ? 'DISABLED' : 'ACTIVE'}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onCalibrateSquare(inspectSquare[0], inspectSquare[1])}
              className="px-3 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold font-display shadow flex items-center gap-1 transition-all"
            >
              <RotateCcw size={13} />
              <span>Set Baseline</span>
            </button>

            <button
              onClick={() => onToggleDisableSquare(inspectSquare[0], inspectSquare[1])}
              className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold font-display border border-slate-700 flex items-center gap-1 transition-all"
            >
              <Ban size={13} />
              <span>{disabledSet.has(`${inspectSquare[0]},${inspectSquare[1]}`) ? 'Enable' : 'Disable'}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
