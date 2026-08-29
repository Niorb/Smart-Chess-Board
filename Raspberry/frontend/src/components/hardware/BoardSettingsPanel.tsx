import React from 'react';
import { 
  Sliders, 
  RotateCcw, 
  BookmarkCheck, 
  Sun, 
  Moon, 
  RefreshCw, 
  ShieldCheck,
  CheckCircle2
} from 'lucide-react';

interface BoardSettingsPanelProps {
  positiveThresh: number;
  setPositiveThresh: (v: number) => void;
  negativeThresh: number;
  setNegativeThresh: (v: number) => void;
  scanDelay: number;
  setScanDelay: (v: number) => void;
  muxSettleMs: number;
  setMuxSettleMs: (v: number) => void;
  debounceThreshold: number;
  setDebounceThreshold: (v: number) => void;
  baselineWindowS: number;
  setBaselineWindowS: (v: number) => void;
  inLoopCalibration: boolean;
  setInLoopCalibration: (v: boolean) => void;
  ledIntensity: number;
  setLedIntensity: (v: number) => void;
  nightMode: boolean;
  setNightMode: (v: boolean) => void;
  piecesMode: 'auto' | 'pieces' | 'empty';
  onSetPiecesMode: (mode: 'auto' | 'pieces' | 'empty') => void;
  onCalibrate: () => void;
  onCalibrateWithPieces: () => void;
  onSaveDefaults: () => void;
  calibrating: boolean;
  savingDefaults: boolean;
  calibrationStatus: string | null;
  saveDefaultsStatus: string | null;
  persistSettings: (overrides?: Record<string, unknown>) => void;
}

export const BoardSettingsPanel: React.FC<BoardSettingsPanelProps> = ({
  positiveThresh,
  setPositiveThresh,
  negativeThresh,
  setNegativeThresh,
  scanDelay,
  setScanDelay,
  muxSettleMs,
  setMuxSettleMs,
  debounceThreshold,
  setDebounceThreshold,
  baselineWindowS,
  setBaselineWindowS,
  inLoopCalibration,
  setInLoopCalibration,
  ledIntensity,
  setLedIntensity,
  nightMode,
  setNightMode,
  piecesMode,
  onSetPiecesMode,
  onCalibrate,
  onCalibrateWithPieces,
  onSaveDefaults,
  calibrating,
  savingDefaults,
  calibrationStatus,
  saveDefaultsStatus,
  persistSettings,
}) => {
  return (
    <div className="glass-panel rounded-3xl p-5 flex flex-col gap-5 text-left shadow-artisan">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-amber-500/20 text-amber-300 border border-amber-500/40">
            <Sliders size={18} />
          </div>
          <div>
            <h3 className="text-sm font-bold font-display text-white">Hardware Calibration &amp; Thresholds</h3>
            <p className="text-[11px] text-slate-400 font-sans">Tune ADC sensitivity, multiplexer timings, and persistent EEPROM baselines</p>
          </div>
        </div>
      </div>

      {/* Global Board Calibration Action Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        <button
          onClick={onCalibrate}
          disabled={calibrating}
          className="p-3.5 rounded-2xl bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-amber-200 text-xs font-bold font-display flex flex-col items-start gap-1 transition-all"
        >
          <div className="flex items-center gap-2">
            <RotateCcw size={14} className={calibrating ? 'animate-spin' : ''} />
            <span>Calibrate Empty Board</span>
          </div>
          <span className="text-[10px] text-amber-300/70 font-sans">Keep all squares clear to sample base magnetic floor</span>
        </button>

        <button
          onClick={onCalibrateWithPieces}
          disabled={calibrating}
          className="p-3.5 rounded-2xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/40 text-cyan-200 text-xs font-bold font-display flex flex-col items-start gap-1 transition-all"
        >
          <div className="flex items-center gap-2">
            <RotateCcw size={14} className={calibrating ? 'animate-spin' : ''} />
            <span>Calibrate With Pieces Set</span>
          </div>
          <span className="text-[10px] text-cyan-300/70 font-sans">Interpolate base from vacant middle ranks</span>
        </button>
      </div>

      {calibrationStatus && (
        <div className="p-2.5 rounded-xl bg-amber-950/60 border border-amber-500/40 text-amber-200 text-xs font-mono">
          {calibrationStatus}
        </div>
      )}

      {/* Threshold & Timing Sliders */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Positive Threshold */}
        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs font-mono font-bold">
            <span className="text-slate-300">Positive Threshold (+Δ)</span>
            <span className="text-emerald-400">+{positiveThresh} ADC</span>
          </div>
          <input
            type="range"
            min="50"
            max="500"
            step="10"
            value={positiveThresh}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              setPositiveThresh(v);
              persistSettings({ pos: v });
            }}
            className="accent-amber-500 cursor-pointer"
          />
        </div>

        {/* Negative Threshold */}
        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs font-mono font-bold">
            <span className="text-slate-300">Negative Threshold (-Δ)</span>
            <span className="text-cyan-400">-{negativeThresh} ADC</span>
          </div>
          <input
            type="range"
            min="50"
            max="500"
            step="10"
            value={negativeThresh}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              setNegativeThresh(v);
              persistSettings({ neg: v });
            }}
            className="accent-amber-500 cursor-pointer"
          />
        </div>

        {/* LED Intensity */}
        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs font-mono font-bold">
            <span className="text-slate-300">LED Brightness</span>
            <span className="text-amber-400">{ledIntensity}%</span>
          </div>
          <input
            type="range"
            min="10"
            max="100"
            step="5"
            value={ledIntensity}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              setLedIntensity(v);
              persistSettings({ intensity: v });
            }}
            className="accent-amber-500 cursor-pointer"
          />
        </div>

        {/* MUX Settle Time */}
        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs font-mono font-bold">
            <span className="text-slate-300">MUX Settle Time</span>
            <span className="text-violet-400">{muxSettleMs} µs</span>
          </div>
          <input
            type="range"
            min="5"
            max="250"
            step="5"
            value={muxSettleMs}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              setMuxSettleMs(v);
              persistSettings({ settle: v });
            }}
            className="accent-amber-500 cursor-pointer"
          />
        </div>
      </div>

      {/* Toggles: In-Loop Calibration & Night Mode */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-800">
        <div className="flex items-center justify-between p-3 rounded-2xl bg-slate-900/60 border border-slate-800">
          <div className="flex flex-col">
            <span className="text-xs font-bold text-slate-200 font-display">In-Loop Calibration</span>
            <span className="text-[10px] text-slate-400 font-sans">Dynamic thermal drift compensation</span>
          </div>
          <button
            onClick={() => {
              const next = !inLoopCalibration;
              setInLoopCalibration(next);
              persistSettings({ inLoopCal: next });
            }}
            className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors ${
              inLoopCalibration ? 'bg-emerald-500' : 'bg-slate-800'
            }`}
          >
            <div
              className={`bg-slate-950 w-4 h-4 rounded-full shadow transform transition-transform ${
                inLoopCalibration ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>

        <div className="flex items-center justify-between p-3 rounded-2xl bg-slate-900/60 border border-slate-800">
          <div className="flex flex-col">
            <span className="text-xs font-bold text-slate-200 font-display">Night Ambient Glow</span>
            <span className="text-[10px] text-slate-400 font-sans">Warm backlight for dim rooms</span>
          </div>
          <button
            onClick={() => {
              const next = !nightMode;
              setNightMode(next);
              persistSettings({ nMode: next });
            }}
            className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors ${
              nightMode ? 'bg-indigo-500' : 'bg-slate-800'
            }`}
          >
            <div
              className={`bg-slate-950 w-4 h-4 rounded-full shadow transform transition-transform ${
                nightMode ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>

      {/* Save Settings as Defaults CTA */}
      <div className="flex flex-col gap-2 pt-2 border-t border-slate-800">
        <button
          onClick={onSaveDefaults}
          disabled={savingDefaults}
          className="w-full py-3 rounded-2xl bg-gradient-to-r from-amber-500 to-amber-600 hover:brightness-110 text-slate-950 font-display font-extrabold text-xs shadow-amber-glow flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {savingDefaults ? (
            <>
              <RefreshCw size={15} className="animate-spin" />
              <span>Saving to Flash EEPROM &amp; board_settings.json...</span>
            </>
          ) : (
            <>
              <BookmarkCheck size={15} />
              <span>Save Current Values as Permanent Board Defaults</span>
            </>
          )}
        </button>

        {saveDefaultsStatus && (
          <div className="p-2.5 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-200 text-xs font-mono flex items-center gap-1.5">
            <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
            <span>{saveDefaultsStatus}</span>
          </div>
        )}
      </div>
    </div>
  );
};
