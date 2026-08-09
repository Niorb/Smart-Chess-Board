import { useState, useEffect, useRef } from 'react'
import { useBoardState } from './hooks/useBoardState'
import { 
  seekGame, 
  cancelGame, 
  getBoardSettings, 
  updateBoardSettings, 
  calibrateBoard,
  makeMove,
  highlightSquare,
  testLeds,
  clearAllLeds
} from './api'
import { 
  Play, 
  XCircle, 
  Grid3X3, 
  Cpu, 
  Settings as SettingsIcon,
  AlertTriangle,
  Terminal,
  Activity,
  Sliders,
  RefreshCw,
  PowerOff
} from 'lucide-react'

function App() {
  const { state, isConnected } = useBoardState();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'play' | 'debug'>('play');

  const [selectedTC, setSelectedTC] = useState<string>('10 min');

  // Click to Move
  const [selectedSquare, setSelectedSquare] = useState<{ col: number; row: number } | null>(null);

  const getChessCoord = (col: number, row: number): string => {
    const file = String.fromCharCode(97 + row);
    const rank = col + 1;
    return `${file}${rank}`;
  };

  const handleSquareClick = async (col: number, row: number) => {
    if (state.status !== 'PLAYING') return;

    if (!selectedSquare) {
      const piece = state.digital[col]?.[row];
      if (piece && piece !== '.') {
        setSelectedSquare({ col, row });
      }
    } else {
      const fromSquare = getChessCoord(selectedSquare.col, selectedSquare.row);
      const toSquare = getChessCoord(col, row);

      if (fromSquare === toSquare) {
        setSelectedSquare(null);
        return;
      }

      setSelectedSquare(null);
      try {
        const res = await makeMove(fromSquare, toSquare);
        if (res.status !== 'success') {
          console.error("Move failed:", res.message);
        }
      } catch (err) {
        console.error("Error making move:", err);
      }
    }
  };

  const handleToggleHighlight = async (col: number, row: number) => {
    try {
      await highlightSquare(col, row);
    } catch (err) {
      console.error("Error toggling highlight:", err);
    }
  };

  const handleTestLeds = async () => {
    try {
      await testLeds();
    } catch (err) {
      console.error("Error running LED test:", err);
    }
  };

  const handleClearLeds = async () => {
    try {
      await clearAllLeds();
    } catch (err) {
      console.error("Error turning off LEDs:", err);
    }
  };

  const handleToggleDisableSquare = async (col: number, row: number) => {
    const currentDisabled = state.physical.disabled_squares ?? [];
    const exists = currentDisabled.some((sq) => sq[0] === col && sq[1] === row);
    let nextDisabled: number[][];
    if (exists) {
      nextDisabled = currentDisabled.filter((sq) => !(sq[0] === col && sq[1] === row));
    } else {
      nextDisabled = [...currentDisabled, [col, row]];
    }
    
    try {
      const res = await updateBoardSettings(
        positiveThresh,
        negativeThresh,
        colMode,
        manualCol,
        scanDelay,
        muxSettleMs,
        debounceThreshold,
        baselineWindowS,
        nextDisabled
      );
      if (res.status === 'success') {
        setSettings(res.settings);
      }
    } catch (err) {
      console.error("Error toggling disabled square:", err);
    }
  };

  // Derived selection state: selection is only valid when state.status === 'PLAYING'
  const activeSelectedSquare = state.status === 'PLAYING' ? selectedSquare : null;

  // Settings & Calibration
  const [settings, setSettings] = useState<{
    baselines: number[][];
    threshold_positive: number;
    threshold_negative: number;
    col_mode?: 'auto' | 'manual';
    manual_col?: number;
    scan_delay?: number;
    mux_settle_ms?: number;
    debounce_threshold?: number;
    baseline_window_s?: number;
    disabled_squares?: number[][];
  } | null>(null);
  const [positiveThresh, setPositiveThresh] = useState<number>(150);
  const [negativeThresh, setNegativeThresh] = useState<number>(150);
  const [colMode, setColMode] = useState<'auto' | 'manual'>('auto');
  const [manualCol, setManualCol] = useState<number>(0);
  const [scanDelay, setScanDelay] = useState<number>(100);
  const [muxSettleMs, setMuxSettleMs] = useState<number>(10);
  const [debounceThreshold, setDebounceThreshold] = useState<number>(2);
  const [baselineWindowS, setBaselineWindowS] = useState<number>(2);
  const [calibrating, setCalibrating] = useState(false);
  const [calibrationStatus, setCalibrationStatus] = useState<string | null>(null);
  const [settingsStatus, setSettingsStatus] = useState<string | null>(null);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await getBoardSettings();
        setSettings(res);
        setPositiveThresh(res.threshold_positive);
        setNegativeThresh(res.threshold_negative);
        setColMode(res.col_mode || 'auto');
        setManualCol(res.manual_col !== undefined ? res.manual_col : 0);
        setScanDelay(res.scan_delay !== undefined ? res.scan_delay : 100);
        setMuxSettleMs(res.mux_settle_ms !== undefined ? res.mux_settle_ms : 10);
        setDebounceThreshold(res.debounce_threshold !== undefined ? res.debounce_threshold : 2);
        setBaselineWindowS(res.baseline_window_s !== undefined ? res.baseline_window_s : 2);
      } catch (err) {
        console.error("Error fetching board settings:", err);
      }
    };
    if (isConnected) {
      fetchSettings();
    }
  }, [isConnected]);

  const isInitialCalibrating = !!state.physical?.initial_calibrating;
  const prevInitialCalibratingRef = useRef(false);

  useEffect(() => {
    if (prevInitialCalibratingRef.current && !isInitialCalibrating) {
      const fetchSettings = async () => {
        try {
          const res = await getBoardSettings();
          setSettings(res);
          setPositiveThresh(res.threshold_positive);
          setNegativeThresh(res.threshold_negative);
          setColMode(res.col_mode || 'auto');
          setManualCol(res.manual_col !== undefined ? res.manual_col : 0);
          setScanDelay(res.scan_delay !== undefined ? res.scan_delay : 100);
          setMuxSettleMs(res.mux_settle_ms !== undefined ? res.mux_settle_ms : 10);
          setDebounceThreshold(res.debounce_threshold !== undefined ? res.debounce_threshold : 2);
          setBaselineWindowS(res.baseline_window_s !== undefined ? res.baseline_window_s : 2);
        } catch (err) {
          console.error("Error fetching board settings after calibration:", err);
        }
      };
      fetchSettings();
    }
    prevInitialCalibratingRef.current = isInitialCalibrating;
  }, [isInitialCalibrating]);


  const handleSeek = async () => {
    setLoading(true);
    try {
      await seekGame(selectedTC);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    setLoading(true);
    try {
      await cancelGame();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCalibrate = async () => {
    setCalibrating(true);
    setCalibrationStatus("Calibrating... Keep board clear");
    try {
      const res = await calibrateBoard();
      if (res.status === 'success') {
        setSettings(res.settings);
        setPositiveThresh(res.settings.threshold_positive);
        setNegativeThresh(res.settings.threshold_negative);
        setScanDelay(res.settings.scan_delay !== undefined ? res.settings.scan_delay : 100);
        setMuxSettleMs(res.settings.mux_settle_ms !== undefined ? res.settings.mux_settle_ms : 10);
        setDebounceThreshold(res.settings.debounce_threshold !== undefined ? res.settings.debounce_threshold : 2);
        setBaselineWindowS(res.settings.baseline_window_s !== undefined ? res.settings.baseline_window_s : 2);
        setCalibrationStatus("Success: Baselines updated!");
      } else {
        setCalibrationStatus("Failed: " + res.message);
      }
    } catch (err) {
      console.error(err);
      setCalibrationStatus("Error: Calibration failed");
    } finally {
      setCalibrating(false);
      setTimeout(() => setCalibrationStatus(null), 4000);
    }
  };

  const handleSaveThresholds = async () => {
    setSettingsStatus("Saving thresholds...");
    const currentDisabled = state.physical.disabled_squares ?? [];
    try {
      const res = await updateBoardSettings(
        positiveThresh,
        negativeThresh,
        colMode,
        manualCol,
        scanDelay,
        muxSettleMs,
        debounceThreshold,
        baselineWindowS,
        currentDisabled
      );
      if (res.status === 'success') {
        setSettings(res.settings);
        setSettingsStatus("Success: Thresholds saved!");
      } else {
        setSettingsStatus("Failed to save");
      }
    } catch (err) {
      console.error(err);
      setSettingsStatus("Error saving thresholds");
    } finally {
      setTimeout(() => setSettingsStatus(null), 4000);
    }
  };

  const handleColModeChange = async (mode: 'auto' | 'manual') => {
    setColMode(mode);
    try {
      const res = await updateBoardSettings(positiveThresh, negativeThresh, mode, manualCol, scanDelay, muxSettleMs, debounceThreshold, baselineWindowS);
      if (res.status === 'success') {
        setSettings(res.settings);
      }
    } catch (err) {
      console.error("Error updating column mode:", err);
    }
  };

  const handleManualColChange = async (col: number) => {
    setManualCol(col);
    try {
      const res = await updateBoardSettings(positiveThresh, negativeThresh, colMode, col, scanDelay, muxSettleMs, debounceThreshold, baselineWindowS);
      if (res.status === 'success') {
        setSettings(res.settings);
      }
    } catch (err) {
      console.error("Error activating column:", err);
    }
  };

  const handleScanDelayChange = async (val: number) => {
    setScanDelay(val);
    try {
      const res = await updateBoardSettings(positiveThresh, negativeThresh, colMode, manualCol, val, muxSettleMs, debounceThreshold, baselineWindowS);
      if (res.status === 'success') {
        setSettings(res.settings);
      }
    } catch (err) {
      console.error("Error updating scan delay:", err);
    }
  };

  const handleMuxSettleMsChange = async (val: number) => {
    setMuxSettleMs(val);
    try {
      const res = await updateBoardSettings(positiveThresh, negativeThresh, colMode, manualCol, scanDelay, val, debounceThreshold, baselineWindowS);
      if (res.status === 'success') {
        setSettings(res.settings);
      }
    } catch (err) {
      console.error("Error updating mux settle delay:", err);
    }
  };

  const handleDebounceThresholdChange = async (val: number) => {
    setDebounceThreshold(val);
    try {
      const res = await updateBoardSettings(positiveThresh, negativeThresh, colMode, manualCol, scanDelay, muxSettleMs, val, baselineWindowS);
      if (res.status === 'success') {
        setSettings(res.settings);
      }
    } catch (err) {
      console.error("Error updating debounce threshold:", err);
    }
  };

  const handleBaselineWindowSChange = async (val: number) => {
    setBaselineWindowS(val);
    try {
      const res = await updateBoardSettings(positiveThresh, negativeThresh, colMode, manualCol, scanDelay, muxSettleMs, debounceThreshold, val);
      if (res.status === 'success') {
        setSettings(res.settings);
      }
    } catch (err) {
      console.error("Error updating baseline window:", err);
    }
  };



// Helper to render the digital piece icons or characters
const PIECE_ICONS_WHITE: Record<string, string> = {
  p: '♙', r: '♖', n: '♘', b: '♗', q: '♕', k: '♔'
};
const PIECE_ICONS_BLACK: Record<string, string> = {
  p: '♟', r: '♜', n: '♞', b: '♝', q: '♛', k: '♚'
};

function renderPiece(p: string) {
  if (p === '.') return null;
  const isWhite = p === p.toUpperCase();
  const piece = p.toLowerCase();
  const icon = isWhite ? PIECE_ICONS_WHITE[piece] : PIECE_ICONS_BLACK[piece];

  return (
    <span className={`text-4xl ${isWhite ? 'text-white' : 'text-slate-900'} drop-shadow-md select-none`}>
      {icon || p}
    </span>
  );
}

  return (
    <div className="min-h-screen w-full bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Header / Status Bar */}
      <header className={`p-4 flex items-center justify-between border-b transition-colors duration-1000 ${
        state.status === 'SEEKING' ? 'border-blue-500/50 bg-blue-900/10' :
        state.status === 'PLAYING' ? 'border-green-500/50 bg-green-900/10' :
        'border-slate-800 bg-slate-900/50'
      }`}>
        <div className="flex items-center gap-4">
          <div className="flex flex-col text-left">
            <h1 className="font-bold text-lg leading-none">Smart Chess</h1>
            <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mt-1">
              Status: <span className="text-blue-400">{state.status}</span>
            </span>
          </div>

          {/* Connection Indicators */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Server Connection Badge */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[9px] font-bold uppercase tracking-wider font-mono ${
              isConnected 
                ? 'bg-green-500/10 text-green-400 border-green-500/20' 
                : 'bg-red-500/10 text-red-400 border-red-500/20'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
              Server: {isConnected ? 'Online' : 'Offline'}
            </div>

            {/* Board Hardware Connection Badge */}
            {(() => {
              if (!isConnected) {
                return (
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-slate-800 bg-slate-900/40 text-slate-500 text-[9px] font-bold uppercase tracking-wider font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-700" />
                    Board: Unknown
                  </div>
                );
              }
              const boardStatus = state.diagnostics?.status ?? 'UNKNOWN';
              let badgeClasses = 'bg-red-500/10 text-red-400 border-red-500/20';
              let dotClasses = 'bg-red-400';
              let statusLabel = 'Board: Offline';

              if (boardStatus === 'OK') {
                badgeClasses = 'bg-emerald-500/10 text-emerald-450 border-emerald-500/20';
                dotClasses = 'bg-emerald-400 animate-pulse';
                statusLabel = 'Board: Connected';
              } else if (boardStatus === 'TIMEOUT') {
                badgeClasses = 'bg-amber-500/10 text-amber-450 border-amber-500/20';
                dotClasses = 'bg-amber-400 animate-pulse';
                statusLabel = 'Board: Timeout';
              }

              return (
                <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[9px] font-bold uppercase tracking-wider font-mono ${badgeClasses}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${dotClasses}`} />
                  {statusLabel}
                </div>
              );
            })()}
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {/* Tab Selector */}
          <div className="flex bg-slate-950/60 p-1 rounded-xl border border-slate-800/80">
            <button 
              onClick={() => setActiveTab('play')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-300 ${
                activeTab === 'play' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:text-white'
              }`}
            >
              Play
            </button>
            <button 
              onClick={() => setActiveTab('debug')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-300 flex items-center gap-1.5 ${
                activeTab === 'debug' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Terminal size={12} />
              Debug
            </button>
          </div>

          <button className="p-2 text-slate-400 hover:text-white transition-colors">
             <SettingsIcon size={20} />
          </button>
        </div>
      </header>

      {/* Initial Calibration Banner */}
      {isInitialCalibrating && (
        <div className="bg-amber-500/15 border-b border-amber-500/30 px-4 py-2.5 flex items-center justify-center gap-3 text-amber-300 text-xs font-semibold animate-pulse shadow-lg">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping flex-shrink-0" />
          <span>⚡ Initial Board Calibration in Progress... Sensor thresholds set to ±1000 for 5s (Please keep board clear)</span>
        </div>
      )}

      {activeTab === 'play' ? (
        <main className="flex-grow p-4 md:p-8 flex flex-col md:flex-row items-center md:items-start justify-center gap-6 md:gap-10 max-w-md md:max-w-6xl mx-auto w-full">
          {/* Left Column: Board */}
          <div className="w-full max-w-md md:max-w-xl lg:max-w-2xl flex-shrink-0">
            
            {/* Opponent Info Header (Clock + Color Indicator) */}
            {state.status === 'PLAYING' && (
              <div className="flex justify-between items-center bg-slate-900/60 border border-slate-800 border-b-0 rounded-t-xl px-4 py-2.5 text-xs">
                <div className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${state.my_color === 'white' ? 'bg-slate-900 border border-slate-700' : 'bg-white'}`} />
                  <span className="text-slate-350 font-bold uppercase tracking-wider">
                     Opponent ({state.my_color === 'white' ? 'Black' : 'White'})
                  </span>
                </div>
                <span className="font-mono text-lg font-bold bg-slate-950 px-3 py-1 rounded border border-slate-850 text-slate-300">
                  {state.my_color === 'white' ? state.clocks?.black : state.clocks?.white}
                </span>
              </div>
            )}

            {/* Main 8x8 Board Visualization */}
            <div className={`relative w-full aspect-square bg-slate-800 rounded-xl overflow-hidden shadow-2xl border-4 border-slate-800 ${state.status === 'PLAYING' ? 'rounded-t-none rounded-b-none border-y-0' : ''}`}>
              <div className="grid grid-cols-8 grid-rows-8 w-full h-full">
                {Array(8).fill(null).map((_, rIdx) => (
                  Array(8).fill(null).map((_, cIdx) => {
                    const isDark = (rIdx + cIdx) % 2 === 1;
                    const isFlipped = state.my_color === 'black';
                    const displayCol = isFlipped ? rIdx : 7 - rIdx;
                    const displayRow = isFlipped ? 7 - cIdx : cIdx;
                    const piece = state.digital[displayCol]?.[displayRow] || '.';
                    
                    return (
                      <div 
                        key={`${rIdx}-${cIdx}`}
                        onClick={() => handleSquareClick(displayCol, displayRow)}
                        className={`flex items-center justify-center relative cursor-pointer ${isDark ? 'bg-slate-700' : 'bg-slate-600'} ${
                          activeSelectedSquare?.col === displayCol && activeSelectedSquare?.row === displayRow
                            ? 'ring-4 ring-yellow-400 ring-inset bg-yellow-400/20'
                            : ''
                        }`}
                      >
                        {renderPiece(piece)}
                      </div>
                    );
                  })
                ))}
              </div>

              {/* 8x8 Physical Overlay (Flips horizontally when playing as Black, hidden during active game) */}
              {state.status !== 'PLAYING' && (
                <div className="absolute top-0 left-0 w-full h-full bg-blue-500/5 border border-blue-500/20 rounded-xl backdrop-blur-[0.5px] z-10 pointer-events-none">
                    <div className="absolute -top-6 left-2 bg-blue-500/90 text-[10px] font-bold px-2 py-0.5 rounded-t uppercase tracking-tighter">
                       Physical Sensors
                    </div>
                    <div className="grid grid-cols-8 grid-rows-8 w-full h-full p-1 gap-1 pointer-events-auto">
                       {Array(8).fill(null).map((_, rIdx) => (
                         Array(8).fill(null).map((_, cIdx) => {
                           const isFlipped = state.my_color === 'black';
                           
                           // Column = Rank (ranks 8-1 on White, 1-8 on Black)
                           // Row = File (files a-h on White, h-a on Black)
                           const fileIdx = isFlipped ? (7 - cIdx) : cIdx;
                           const rankIdx = isFlipped ? rIdx : (7 - rIdx);
                           
                           const sensorRank = rankIdx; 
                           const sensorFile = fileIdx; 
                           
                           const sensorStateVal = state.physical.grid?.[sensorFile]?.[sensorRank] ?? 0;
                           const isHighlighted = state.physical.highlighted_square?.[0] === sensorFile && state.physical.highlighted_square?.[1] === sensorRank;
                           const isDisabled = (state.physical.disabled_squares ?? []).some(
                             (sq) => sq[0] === sensorFile && sq[1] === sensorRank
                           );
                           
                           let bgClass = 'bg-slate-900/40';
                           if (isDisabled) {
                             bgClass = 'bg-slate-950/80 border border-slate-900/40 opacity-25 cursor-not-allowed';
                           } else if (isHighlighted) {
                             bgClass = 'bg-orange-500/80 shadow-[0_0_8px_rgba(249,115,22,0.6)] ring-2 ring-orange-400';
                           } else if (sensorStateVal === 1) {
                             bgClass = 'bg-red-500/80 shadow-[0_0_8px_rgba(239,68,68,0.6)]';
                           } else if (sensorStateVal === -1) {
                             bgClass = 'bg-emerald-500/80 shadow-[0_0_8px_rgba(16,185,129,0.6)]';
                           }
                           
                           return (
                             <div 
                               key={`sensor-${rIdx}-${cIdx}`}
                               onClick={() => {
                                 if (!isDisabled) {
                                   handleToggleHighlight(sensorFile, sensorRank);
                                 }
                               }}
                               onContextMenu={(e) => {
                                 e.preventDefault();
                                 handleToggleDisableSquare(sensorFile, sensorRank);
                               }}
                               className={`rounded-sm transition-all duration-300 cursor-pointer ${isDisabled ? '' : 'hover:bg-slate-800/50'} ${bgClass}`}
                             />
                           );
                         })
                       ))}
                    </div>
                </div>
              )}
            </div>

            {/* Player Info Footer (Clock + Color Indicator) */}
            {state.status === 'PLAYING' && (
              <div className="flex justify-between items-center bg-slate-900/60 border border-slate-800 border-t-0 rounded-b-xl px-4 py-2.5 text-xs">
                <div className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${state.my_color === 'white' ? 'bg-white' : 'bg-slate-900 border border-slate-700'}`} />
                  <span className="text-slate-350 font-bold uppercase tracking-wider">
                     You ({state.my_color === 'white' ? 'White' : 'Black'})
                  </span>
                </div>
                <span className="font-mono text-lg font-bold bg-slate-950 px-3 py-1 rounded border border-slate-850 text-blue-400">
                  {state.my_color === 'white' ? state.clocks?.white : state.clocks?.black}
                </span>
              </div>
            )}
          </div>

          {/* Right Column: Status & Controls */}
          <div className="w-full flex flex-col gap-6 md:self-stretch justify-between flex-1 max-w-md">
            <div className="flex flex-col gap-4">
              {/* System & Game Status Info Card */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 shadow-lg">
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">System & Game Status</h2>
                <div className="flex justify-between py-2 border-b border-slate-800/60 text-sm">
                  <span className="text-slate-400">Board Connection</span>
                  <span className={`font-semibold flex items-center gap-1.5 ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
                    <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`}></span>
                    {isConnected ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
                <div className="flex justify-between py-2 border-b border-slate-800/60 text-sm">
                  <span className="text-slate-400">Game State</span>
                  <span className="font-semibold uppercase text-blue-400">{state.status}</span>
                </div>
                {state.status === 'PLAYING' && state.my_color && (
                  <div className="flex justify-between py-2 border-b border-slate-800/60 text-sm">
                    <span className="text-slate-400">Playing As</span>
                    <span className="font-semibold uppercase text-white">{state.my_color}</span>
                  </div>
                )}
              </div>

              {/* Info & Alerts */}
              {state.status === 'SEEKING' && (
                <div className="w-full bg-blue-900/20 border border-blue-500/30 p-3 rounded-lg flex items-center gap-3 animate-pulse">
                  <Grid3X3 className="text-blue-400 shrink-0" />
                  <p className="text-sm text-blue-200">Looking for a match on Chess.com...</p>
                </div>
              )}

              {state.status === 'PLAYING' && state.my_color && (
                <div className="w-full bg-green-900/20 border border-green-500/30 p-3 rounded-lg flex items-center justify-between animate-pulse">
                  <div className="flex items-center gap-3">
                     <Cpu className="text-green-400 shrink-0" />
                     <p className="text-sm text-green-200 uppercase font-bold tracking-widest">
                        Match In Progress
                     </p>
                  </div>
                </div>
              )}

              {!isConnected && (
                 <div className="w-full bg-red-900/20 border border-red-500/30 p-3 rounded-lg flex items-center gap-3">
                  <AlertTriangle className="text-red-400 shrink-0" />
                  <p className="text-sm text-red-200">Cannot reach Pi. Is it on the same Wi-Fi?</p>
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="w-full flex flex-col gap-3 pb-8 md:pb-0 md:mt-auto">
              {/* Time Control Selector */}
              {state.status === 'IDLE' && (
                <div className="w-full flex flex-col gap-2 mb-2 text-left">
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-500">
                     Select Time Control
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                     {[
                       { id: '1 min', label: '1 min', sub: 'Bullet' },
                       { id: '3 min', label: '3 min', sub: 'Blitz' },
                       { id: '5 min', label: '5 min', sub: 'Blitz' },
                       { id: '10 min', label: '10 min', sub: 'Rapid' },
                       { id: '15 | 10', label: '15 | 10', sub: 'Rapid' },
                       { id: '30 min', label: '30 min', sub: 'Rapid' },
                     ].map((tc) => (
                       <button
                         key={tc.id}
                         disabled={loading || !isConnected}
                         onClick={() => setSelectedTC(tc.id)}
                         className={`flex flex-col items-center justify-center p-2 rounded-xl border transition-all duration-300 ${
                           selectedTC === tc.id
                             ? 'bg-blue-600/20 border-blue-500 text-blue-100 shadow-md shadow-blue-900/10'
                             : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-white'
                         }`}
                       >
                         <span className="text-xs font-bold font-mono">{tc.label}</span>
                         <span className="text-[9px] uppercase tracking-wider opacity-60 mt-0.5">{tc.sub}</span>
                       </button>
                     ))}
                  </div>
                </div>
              )}

              {state.status === 'IDLE' ? (
                <button 
                  onClick={handleSeek}
                  disabled={loading || !isConnected}
                  className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500 py-4 rounded-2xl font-bold text-lg flex items-center justify-center gap-2 transition-all active:scale-95 shadow-lg shadow-blue-900/20"
                >
                  <Play size={24} fill="currentColor" />
                  Seek Game ({selectedTC})
                </button>
              ) : (
                <button 
                  onClick={handleCancel}
                  disabled={loading}
                  className="w-full bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 py-4 rounded-2xl font-bold text-lg flex items-center justify-center gap-2 transition-all active:scale-95"
                >
                  <XCircle size={24} />
                  {state.status === 'SEEKING' ? 'Cancel Search' : 'Resign Game'}
                </button>
              )}
            </div>
          </div>
        </main>
      ) : (
        <main className="flex-grow p-4 md:p-8 flex flex-col md:flex-row items-center md:items-start justify-center gap-6 md:gap-10 max-w-md md:max-w-6xl mx-auto w-full">
          {/* Left Column: Debug Panel with Sub-tabs */}
          <div className="w-full max-w-md md:max-w-xl lg:max-w-2xl flex-shrink-0">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl flex flex-col gap-6">
               <div className="flex items-center gap-2">
                  <Activity className="text-blue-400" size={24} />
                  <h2 className="text-lg font-bold">Physical ADC Diagnostics</h2>
               </div>
                   <div className="flex justify-between items-center bg-slate-950 p-3 rounded-xl border border-slate-850 text-xs">
                      <span className="text-slate-400">Deviation Thresholds</span>
                      <span className="font-mono text-blue-400 font-bold">+{positiveThresh} / -{negativeThresh}</span>
                   </div>

                   {/* 8x8 Diagnostic Grid */}
                   <div className="grid grid-cols-8 gap-2 w-full">
                      {Array(8).fill(null).map((_, rIdx) => {
                        return Array(8).fill(null).map((_, cIdx) => {
                          const sensorRank = 7 - rIdx;
                          const sensorFile = cIdx;
                          const rawAdc = state.physical.adc?.[sensorFile]?.[sensorRank] ?? 0;
                          const sensorStateVal = state.physical.grid?.[sensorFile]?.[sensorRank] ?? 0;
                          const baseline = state.physical.baselines?.[sensorFile]?.[sensorRank] ?? settings?.baselines?.[sensorFile]?.[sensorRank] ?? 1550;
                          const diffVal = rawAdc - baseline;
                          
                          const file = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'][sensorFile];
                          const rank = sensorRank + 1;
                          const chessCoord = `${file}${rank}`;

                          const isColActive = colMode === 'auto' || sensorFile === manualCol;
                          let cardClass = 'bg-slate-950 border-slate-855 text-slate-300';
                          let statusText = 'IDLE';
                          let statusColorClass = 'text-slate-650';
                          let dotColorClass = 'bg-slate-800';

                          const isHighlighted = state.physical.highlighted_square?.[0] === sensorFile && state.physical.highlighted_square?.[1] === sensorRank;
                          const isDisabled = (state.physical.disabled_squares ?? []).some(
                            (sq) => sq[0] === sensorFile && sq[1] === sensorRank
                          );

                          if (isDisabled) {
                            cardClass = 'bg-slate-950/20 border-slate-900/40 text-slate-600 opacity-40 line-through';
                            statusText = 'DISABLED';
                            statusColorClass = 'text-slate-700';
                            dotColorClass = 'bg-slate-900';
                          } else if (isHighlighted) {
                            cardClass = 'bg-orange-950/40 border-orange-500/80 shadow-[0_0_15px_rgba(249,115,22,0.15)] text-orange-105 ring-2 ring-orange-500/40';
                            statusText = 'HIGHLIGHT';
                            statusColorClass = 'text-orange-400';
                            dotColorClass = 'bg-orange-450 animate-pulse';
                          } else if (sensorStateVal === 1) {
                            cardClass = 'bg-red-950/40 border-red-500/80 shadow-[0_0_15px_rgba(239,68,68,0.15)] text-red-105';
                            statusText = 'NORTH (+)';
                            statusColorClass = 'text-red-400';
                            dotColorClass = 'bg-red-400 animate-pulse';
                          } else if (sensorStateVal === -1) {
                            cardClass = 'bg-emerald-950/40 border-emerald-500/80 shadow-[0_0_15px_rgba(16,185,129,0.15)] text-emerald-105';
                            statusText = 'SOUTH (-)';
                            statusColorClass = 'text-emerald-400';
                            dotColorClass = 'bg-emerald-400 animate-pulse';
                          }

                          // Highlight col selection visually in manual mode
                          const colDiagClass = isColActive ? 'opacity-100 scale-100' : 'opacity-25 scale-95 border-slate-900/60 pointer-events-none select-none';
                          if (colMode === 'manual' && isColActive && !isHighlighted && !isDisabled) {
                            cardClass += ' ring-2 ring-blue-500/40 bg-slate-900/20';
                          }

                          return (
                            <div 
                              key={`debug-sensor-${sensorFile}-${sensorRank}`}
                              onClick={() => {
                                if (!isDisabled) {
                                  handleToggleHighlight(sensorFile, sensorRank);
                                }
                              }}
                              onContextMenu={(e) => {
                                e.preventDefault();
                                handleToggleDisableSquare(sensorFile, sensorRank);
                              }}
                              className={`flex flex-col justify-between p-1.5 rounded-lg border transition-all duration-300 cursor-pointer hover:bg-slate-900/60 ${cardClass} ${colDiagClass}`}
                            >
                              <div className="flex justify-between items-center w-full">
                                 <span className="text-[9px] uppercase font-bold text-slate-500 font-mono">
                                    {chessCoord}
                                 </span>
                                 <span className="text-[7px] text-slate-655 font-mono">
                                    [{sensorFile},{sensorRank}]
                                 </span>
                              </div>
                              
                              <div className="text-center my-auto py-1">
                                 <span className={`text-sm font-bold font-mono tracking-tight block ${
                                   isHighlighted ? 'text-orange-400' : sensorStateVal === 1 ? 'text-red-400' : sensorStateVal === -1 ? 'text-emerald-400' : 'text-slate-200'
                                 }`}>
                                    {diffVal > 0 ? `+${diffVal}` : diffVal}
                                 </span>
                                 <span className="text-[7px] text-slate-605 font-mono block">
                                    Base: {baseline}
                                 </span>
                              </div>

                              <div className="flex justify-between items-center w-full mt-0.5">
                                 <span className={`text-[7px] font-bold uppercase ${statusColorClass}`}>
                                    {statusText}
                                 </span>
                                 <div className={`w-1 h-1 rounded-full ${dotColorClass}`} />
                              </div>
                            </div>
                          );
                        });
                      })}
                   </div>
            </div>
          </div>

          {/* Right Column: Calibration Info & Diagnostics */}
          <div className="w-full flex flex-col gap-6 md:self-stretch justify-between flex-1 max-w-md">
             <div className="flex flex-col gap-6">
                {/* Diagnostics and threshold guide */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col gap-4">
                   <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Diagnostic Info</h3>
                   <div className="text-sm text-slate-400 leading-relaxed">
                      Analog Hall effect sensors output a voltage proportional to the magnetic field.
                      Approaching magnets shift the voltage up or down depending on the pole.
                   </div>
                   <div className="bg-slate-950 p-4 rounded-xl border border-slate-850/60 flex flex-col gap-2">
                      <div className="flex justify-between text-xs py-1 border-b border-slate-800/40">
                         <span className="text-slate-400">Auto-Calibration</span>
                         <span className="text-emerald-400 font-bold uppercase tracking-wider text-[9px] animate-pulse">Active (4s Avg)</span>
                      </div>
                      <div className="flex justify-between text-xs py-1 border-b border-slate-800/40">
                         <span className="text-slate-400">Normal Idle Value</span>
                         <span className="text-slate-200 font-mono">~1550</span>
                      </div>
                      <div className="flex justify-between text-xs py-1">
                         <span className="text-slate-400">Magnet Detections</span>
                         <span className="text-blue-400 font-mono">North (+) &gt; 1700 | South (-) &lt; 1400</span>
                      </div>
                   </div>
                 </div>

                 {/* Calibration & Threshold controls */}
                 <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col gap-4">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                       <Sliders size={16} className="text-blue-400" />
                       Calibration & Thresholds
                    </h3>
                    
                    <div className="flex flex-col gap-4">
                       {/* Positive Threshold Slider */}
                       <div className="flex flex-col gap-1.5 text-left">
                          <div className="flex justify-between items-center text-xs">
                             <span className="text-slate-400">Upper Threshold (+)</span>
                             <div className="flex items-center gap-1 font-mono text-red-400 font-bold">
                                <span>+</span>
                                <input
                                  type="number"
                                  min="50"
                                  max="3000"
                                  value={positiveThresh}
                                  onChange={(e) => {
                                    const val = parseInt(e.target.value);
                                    setPositiveThresh(isNaN(val) ? 0 : Math.min(3000, Math.max(0, val)));
                                  }}
                                  className="w-16 bg-slate-950 border border-slate-800 rounded px-1.5 py-0.5 text-right text-xs font-mono text-red-400 font-bold focus:outline-none focus:border-red-500"
                                />
                             </div>
                          </div>
                          <input 
                            type="range"
                            min="50"
                            max="3000"
                            step="10"
                            value={positiveThresh}
                            onChange={(e) => setPositiveThresh(parseInt(e.target.value))}
                            className="w-full h-1 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-red-500"
                          />
                       </div>

                       {/* Negative Threshold Slider */}
                       <div className="flex flex-col gap-1.5 text-left">
                          <div className="flex justify-between items-center text-xs">
                             <span className="text-slate-400">Lower Threshold (-)</span>
                             <div className="flex items-center gap-1 font-mono text-emerald-400 font-bold">
                                <span>-</span>
                                <input
                                  type="number"
                                  min="50"
                                  max="3000"
                                  value={negativeThresh}
                                  onChange={(e) => {
                                    const val = parseInt(e.target.value);
                                    setNegativeThresh(isNaN(val) ? 0 : Math.min(3000, Math.max(0, val)));
                                  }}
                                  className="w-16 bg-slate-950 border border-slate-800 rounded px-1.5 py-0.5 text-right text-xs font-mono text-emerald-400 font-bold focus:outline-none focus:border-emerald-500"
                                />
                             </div>
                          </div>
                          <input 
                            type="range"
                            min="50"
                            max="3000"
                            step="10"
                            value={negativeThresh}
                            onChange={(e) => setNegativeThresh(parseInt(e.target.value))}
                            className="w-full h-1 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                          />
                       </div>
                        {/* Debounce Threshold Slider */}
                        <div className="flex flex-col gap-1.5 text-left">
                           <div className="flex justify-between items-center text-xs">
                              <span className="text-slate-400">Debounce Threshold (scans)</span>
                              <span className="font-mono text-purple-400 font-bold">{debounceThreshold}</span>
                           </div>
                           <input 
                             type="range"
                             min="1"
                             max="10"
                             step="1"
                             value={debounceThreshold}
                             onChange={(e) => handleDebounceThresholdChange(parseInt(e.target.value))}
                             className="w-full h-1 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-purple-500"
                           />
                        </div>

                        {/* Baseline Window Slider */}
                         <div className="flex flex-col gap-1.5 text-left">
                            <div className="flex justify-between items-center text-xs">
                               <span className="text-slate-400">Auto-Calib Window (sec)</span>
                               <span className="font-mono text-amber-400 font-bold">{baselineWindowS}s</span>
                            </div>
                            <input 
                              type="range"
                              min="1"
                              max="20"
                              step="1"
                              value={baselineWindowS}
                              onChange={(e) => handleBaselineWindowSChange(parseInt(e.target.value))}
                              className="w-full h-1 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-amber-500"
                            />
                         </div>

                       {/* Save Thresholds Button */}
                       <button
                         onClick={handleSaveThresholds}
                         disabled={loading || calibrating}
                         className="w-full bg-slate-950 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 py-2 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 flex items-center justify-center gap-2"
                       >
                          Apply Thresholds
                       </button>
                       {settingsStatus && (
                          <div className="text-center text-[11px] text-blue-400 font-bold font-mono">
                             {settingsStatus}
                          </div>
                       )}

                       <hr className="border-slate-800/60 my-1" />

                       {/* Calibrate Button */}
                       <button
                          onClick={handleCalibrate}
                          disabled={loading || calibrating || !isConnected}
                          className="w-full bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 border border-blue-500/20 py-3 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 flex items-center justify-center gap-2"
                        >
                           <RefreshCw size={14} className={calibrating ? 'animate-spin' : ''} />
                           {calibrating ? 'Recalibrating...' : 'Force Recalibrate Baselines'}
                        </button>
                       
                       {calibrationStatus && (
                          <div className={`text-center text-[11px] font-bold font-mono ${
                             calibrationStatus.startsWith('Success') ? 'text-green-400' : 
                             calibrationStatus.startsWith('Failed') || calibrationStatus.startsWith('Error') ? 'text-red-400' :
                             'text-slate-400 animate-pulse'
                          }`}>
                             {calibrationStatus}
                          </div>
                       )}

                        {/* Diagnostic LED test button */}
                        <button
                          onClick={handleTestLeds}
                          disabled={loading || calibrating || !isConnected || state.physical.led_test_active}
                          className="w-full bg-orange-655 hover:bg-orange-500 disabled:bg-slate-800 disabled:text-slate-500 py-3 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 flex items-center justify-center gap-2 shadow-lg shadow-orange-950/20"
                        >
                           <Activity size={14} />
                           {state.physical.led_test_active ? `Testing LED ${state.physical.testing_led_index}...` : 'Diagnostic LED Test'}
                        </button>

                        {/* Force All LEDs Off button */}
                        <button
                          onClick={handleClearLeds}
                          disabled={loading || calibrating || !isConnected}
                          className="w-full bg-rose-600/10 hover:bg-rose-600/20 text-rose-400 border border-rose-500/20 disabled:bg-slate-800 disabled:text-slate-500 disabled:border-slate-800 py-3 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 flex items-center justify-center gap-2 shadow-lg shadow-rose-950/10"
                        >
                           <PowerOff size={14} />
                           Force All LEDs Off
                        </button>
                    </div>
                 </div>

                  {/* Column Activation Diagnostics */}
                  <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col gap-4">
                     <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <Cpu size={16} className="text-blue-400" />
                        Column Activation Diagnostics
                     </h3>
                     <div className="text-xs text-slate-400 leading-relaxed text-left">
                        Control which columns are physically scanned. Lock a column to diagnose wiring issues or crosstalk.
                     </div>
                     
                     <div className="flex flex-col gap-3">
                        <div className="flex flex-col gap-1.5 text-left">
                           <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Activation Mode</label>
                           <div className="grid grid-cols-2 gap-2">
                              <button
                                onClick={() => handleColModeChange('auto')}
                                className={`py-2 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 ${
                                  colMode === 'auto'
                                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/10'
                                    : 'bg-slate-950 hover:bg-slate-850 border border-slate-850 text-slate-400 hover:text-white'
                                }`}
                              >
                                 Automatic
                              </button>
                              <button
                                onClick={() => handleColModeChange('manual')}
                                className={`py-2 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 ${
                                  colMode === 'manual'
                                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/10'
                                    : 'bg-slate-950 hover:bg-slate-855 border border-slate-850 text-slate-400 hover:text-white'
                                }`}
                              >
                                 Manual
                              </button>
                           </div>
                        </div>

                        {colMode === 'manual' && (
                           <div className="flex flex-col gap-1.5 text-left transition-all duration-350 animate-fadeIn">
                              <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Active Column Select</label>
                              <div className="grid grid-cols-5 gap-1.5">
                                 {[0, 1, 2, 3, 4, 5, 6, 7, -1].map((col) => (
                                    <button
                                      key={`col-select-${col}`}
                                      onClick={() => handleManualColChange(col)}
                                      className={`py-2 rounded-xl text-xs font-bold transition-all duration-300 ${
                                        manualCol === col
                                          ? 'bg-red-655 text-white border border-red-500 shadow-md shadow-red-950/20'
                                          : 'bg-slate-950 hover:bg-slate-850 border border-slate-850 text-slate-400 hover:text-white'
                                      }`}
                                    >
                                       {col === -1 ? 'None' : `C${col}`}
                                    </button>
                                 ))}
                              </div>
                              <p className="text-[10px] text-slate-550 mt-1 leading-normal border-b border-slate-800/60 pb-3">
                                 Locking a column sets other columns to channel 15 on the MUX. They should read baseline values (~1550).
                              </p>

                              <div className="flex flex-col gap-1.5 mt-2">
                                 <div className="flex justify-between items-center text-xs">
                                    <span className="text-slate-400 font-bold uppercase tracking-wider text-[10px]">Manual Scan Delay</span>
                                    <span className="font-mono text-blue-400 font-bold">{scanDelay} ms</span>
                                 </div>
                                 <input 
                                   type="range"
                                   min="50"
                                   max="2000"
                                   step="50"
                                   value={scanDelay}
                                   onChange={(e) => handleScanDelayChange(parseInt(e.target.value))}
                                   className="w-full h-1 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                 />
                                 <p className="text-[10px] text-slate-550 leading-normal">
                                    Adjust how long to pause between matrix scans to make tracking raw values easier.
                                 </p>
                              </div>

                              <div className="flex flex-col gap-1.5 mt-3 pt-3 border-t border-slate-800/40">
                                 <div className="flex justify-between items-center text-xs">
                                    <span className="text-slate-400 font-bold uppercase tracking-wider text-[10px]">MUX Settle Delay</span>
                                    <span className="font-mono text-emerald-400 font-bold">{muxSettleMs} ms</span>
                                 </div>
                                 <input 
                                   type="range"
                                   min="1"
                                   max="50"
                                   step="1"
                                   value={muxSettleMs}
                                   onChange={(e) => handleMuxSettleMsChange(parseInt(e.target.value))}
                                   className="w-full h-1 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                                 />
                                 <p className="text-[10px] text-slate-550 leading-normal">
                                    Increase this if raw sensor values are unstable or noisy when switching channels.
                                 </p>
                              </div>
                           </div>
                        )}
                     </div>
                  </div>

                {/* System status card duplicate for debug view */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 shadow-lg">
                  <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">System & Game Status</h2>
                  <div className="flex justify-between py-2 border-b border-slate-800/60 text-sm">
                    <span className="text-slate-400">Board Connection</span>
                    <span className={`font-semibold flex items-center gap-1.5 ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
                      <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`}></span>
                      {isConnected ? 'Connected' : 'Disconnected'}
                    </span>
                  </div>
                  <div className="flex justify-between py-2 border-b border-slate-800/60 text-sm">
                    <span className="text-slate-400">Game State</span>
                    <span className="font-semibold uppercase text-blue-400">{state.status}</span>
                  </div>
                </div>
             </div>
          </div>
        </main>
      )}

      <footer className="p-4 text-center border-t border-slate-900">
         <p className="text-[10px] text-slate-600 uppercase font-bold tracking-[0.2em]">
            Pi 4B Connected • Headless Engine v1.0
         </p>
      </footer>
    </div>
  )
}

export default App
