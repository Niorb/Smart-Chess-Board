import React, { useState } from 'react';
import { AdcSensorMatrix } from './AdcSensorMatrix';
import { LedTesterControl } from './LedTesterControl';
import { BoardSettingsPanel } from './BoardSettingsPanel';
import { Activity, Sparkles, Sliders } from 'lucide-react';
import type { BoardState } from '../../hooks/useBoardState';

interface HardwareWorkshopProps {
  state: BoardState;
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
  onCalibrateSquare: (col: number, row: number) => void;
  onToggleDisableSquare: (col: number, row: number) => void;
  onTestLeds: () => void;
  onClearLeds: () => void;
  onTriggerAnimation: (name: string, params?: Record<string, unknown>) => void;
  onTestTrace: (uci: string, isCapture?: boolean) => void;
}

export const HardwareWorkshop: React.FC<HardwareWorkshopProps> = ({
  state,
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
  onCalibrateSquare,
  onToggleDisableSquare,
  onTestLeds,
  onClearLeds,
  onTriggerAnimation,
  onTestTrace,
}) => {
  const [tab, setTab] = useState<'matrix' | 'leds' | 'calibration'>('matrix');

  return (
    <div className="w-full flex flex-col gap-5 max-w-5xl mx-auto">
      {/* Workshop Navigation Tabs */}
      <div className="flex items-center justify-center">
        <div className="glass-panel p-1.5 rounded-2xl flex items-center gap-1.5 shadow-md">
          <button
            onClick={() => setTab('matrix')}
            className={`px-4 py-2 rounded-xl text-xs font-display font-bold flex items-center gap-2 transition-all ${
              tab === 'matrix'
                ? 'bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 shadow-amber-glow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Activity size={15} />
            <span>ADC Sensor Heatmap</span>
          </button>

          <button
            onClick={() => setTab('leds')}
            className={`px-4 py-2 rounded-xl text-xs font-display font-bold flex items-center gap-2 transition-all ${
              tab === 'leds'
                ? 'bg-gradient-to-r from-cyan-500 to-cyan-600 text-slate-950 shadow-cyan-glow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Sparkles size={15} />
            <span>LED Test Bench</span>
          </button>

          <button
            onClick={() => setTab('calibration')}
            className={`px-4 py-2 rounded-xl text-xs font-display font-bold flex items-center gap-2 transition-all ${
              tab === 'calibration'
                ? 'bg-gradient-to-r from-violet-500 to-violet-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Sliders size={15} />
            <span>Board Calibration</span>
          </button>
        </div>
      </div>

      {/* Main Views */}
      {tab === 'matrix' && (
        <AdcSensorMatrix
          adcGrid={state.physical?.adc}
          baselines={state.physical?.baselines}
          disabledSquares={state.physical?.disabled_squares}
          positiveThresh={positiveThresh}
          negativeThresh={negativeThresh}
          onCalibrateSquare={onCalibrateSquare}
          onToggleDisableSquare={onToggleDisableSquare}
        />
      )}

      {tab === 'leds' && (
        <LedTesterControl
          onTestLeds={onTestLeds}
          onClearLeds={onClearLeds}
          onTriggerAnimation={onTriggerAnimation}
          onTestTrace={onTestTrace}
        />
      )}

      {tab === 'calibration' && (
        <BoardSettingsPanel
          positiveThresh={positiveThresh}
          setPositiveThresh={setPositiveThresh}
          negativeThresh={negativeThresh}
          setNegativeThresh={setNegativeThresh}
          scanDelay={scanDelay}
          setScanDelay={setScanDelay}
          muxSettleMs={muxSettleMs}
          setMuxSettleMs={setMuxSettleMs}
          debounceThreshold={debounceThreshold}
          setDebounceThreshold={setDebounceThreshold}
          baselineWindowS={baselineWindowS}
          setBaselineWindowS={setBaselineWindowS}
          inLoopCalibration={inLoopCalibration}
          setInLoopCalibration={setInLoopCalibration}
          ledIntensity={ledIntensity}
          setLedIntensity={setLedIntensity}
          nightMode={nightMode}
          setNightMode={setNightMode}
          piecesMode={piecesMode}
          onSetPiecesMode={onSetPiecesMode}
          onCalibrate={onCalibrate}
          onCalibrateWithPieces={onCalibrateWithPieces}
          onSaveDefaults={onSaveDefaults}
          calibrating={calibrating}
          savingDefaults={savingDefaults}
          calibrationStatus={calibrationStatus}
          saveDefaultsStatus={saveDefaultsStatus}
          persistSettings={persistSettings}
        />
      )}
    </div>
  );
};
