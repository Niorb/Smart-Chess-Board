import { useState, useEffect, useMemo } from 'react'
import { useBoardState } from './hooks/useBoardState'
import { 
  seekGame, 
  cancelGame, 
  resignGame,
  offerDraw,
  getLichessAccount,
  setGameMode,
  getBoardSettings, 
  updateBoardSettings, 
  calibrateBoard,
  calibrateBoardWithPieces,
  makeMove,
  highlightSquare,
  testLeds,
  clearAllLeds,
  triggerAnimation,
  testMoveTrace
} from './api'
import type { LichessAccount } from './api'
import { 
  Play, 
  XCircle, 
  Flag,
  Handshake,
  Terminal,
  Activity,
  Sliders,
  RefreshCw,
  PowerOff,
  User,
  Shield,
  Layers,
  CheckCircle2,
  Bot,
  Zap,
  Target,
  Sparkles,
  Wand2
} from 'lucide-react'

// Helper to render digital piece characters/icons
const PIECE_ICONS_WHITE: Record<string, string> = {
  p: '♙', r: '♖', n: '♘', b: '♗', q: '♕', k: '♔'
};
const PIECE_ICONS_BLACK: Record<string, string> = {
  p: '♟', r: '♜', n: '♞', b: '♝', q: '♛', k: '♚'
};

function renderPiece(p: string) {
  if (!p || p === '.') return null;
  const isWhite = p === p.toUpperCase();
  const piece = p.toLowerCase();
  const icon = isWhite ? PIECE_ICONS_WHITE[piece] : PIECE_ICONS_BLACK[piece];

  return (
    <span className={`text-4xl ${isWhite ? 'text-slate-100 drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]' : 'text-slate-900 drop-shadow-[0_2px_4px_rgba(255,255,255,0.3)]'} select-none transition-transform hover:scale-105`}>
      {icon || p}
    </span>
  );
}

function App() {
  const { state, isConnected } = useBoardState();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'play' | 'debug'>('play');

  // Lichess Account info
  const [account, setAccount] = useState<LichessAccount | null>(null);

  // Time control & match settings
  const [selectedTC, setSelectedTC] = useState<string>('10+0');
  const [isRated, setIsRated] = useState<boolean>(true);
  const [selectedColor, setSelectedColor] = useState<'random' | 'white' | 'black'>('random');
  const [opponentMode, setOpponentMode] = useState<'auto' | 'ai' | 'human'>('auto');
  const [aiLevel, setAiLevel] = useState<number>(3);
  const [ratingBoundary, setRatingBoundary] = useState<'any' | '100' | '200' | '300' | '500' | 'custom'>('any');
  const [customMinRating, setCustomMinRating] = useState<string>('1200');
  const [customMaxRating, setCustomMaxRating] = useState<string>('1800');

  // Calculate target rating range string for Lichess seek (e.g., "1350-1750")
  const computedRatingRange = useMemo(() => {
    if (ratingBoundary === 'any') return undefined;
    if (ratingBoundary === 'custom') {
      const min = parseInt(customMinRating);
      const max = parseInt(customMaxRating);
      if (!isNaN(min) && !isNaN(max) && min < max) {
        return `${min}-${max}`;
      }
      return undefined;
    }
    const delta = parseInt(ratingBoundary);
    if (!isNaN(delta)) {
      const userRating = account?.rating || 1500;
      const min = Math.max(800, userRating - delta);
      const max = Math.min(2900, userRating + delta);
      return `${min}-${max}`;
    }
    return undefined;
  }, [ratingBoundary, customMinRating, customMaxRating, account?.rating]);

  // Click to Move state
  const [selectedSquare, setSelectedSquare] = useState<{ col: number; row: number } | null>(null);
  const [pendingPromotion, setPendingPromotion] = useState<{ from: string; to: string } | null>(null);

  // Fetch Lichess Account on mount and connection changes
  useEffect(() => {
    const fetchAccount = async () => {
      try {
        const data = await getLichessAccount();
        setAccount(data);
      } catch (err) {
        console.warn("Could not fetch Lichess account:", err);
      }
    };
    if (isConnected) {
      fetchAccount();
    }
  }, [isConnected]);

  // Algebraic coordinate helper: col is rank index (0..7 -> 1..8), row is file index (0..7 -> a..h)
  const getChessCoord = (col: number, row: number): string => {
    const file = String.fromCharCode(97 + row);
    const rank = col + 1;
    return `${file}${rank}`;
  };

  // Compute legal destination squares for the currently selected square
  const legalDestinations = useMemo(() => {
    if (!selectedSquare || state.status !== 'PLAYING') return new Set<string>();
    const fromCoord = getChessCoord(selectedSquare.col, selectedSquare.row);
    const moves = state.game?.legal_moves ?? [];
    const dests = new Set<string>();
    for (const m of moves) {
      if (m.startsWith(fromCoord)) {
        dests.add(m.slice(2, 4));
      }
    }
    return dests;
  }, [selectedSquare, state.status, state.game?.legal_moves]);

  // Last move squares
  const lastMoveSquares = useMemo(() => {
    const lm = state.game?.last_move;
    if (!lm || lm.length < 4) return null;
    return {
      from: lm.slice(0, 2),
      to: lm.slice(2, 4),
    };
  }, [state.game?.last_move]);

  // Check state location
  const kingInCheckCoord = useMemo(() => {
    if (!state.game?.is_check || state.status !== 'PLAYING') return null;
    const turn = state.game.turn;
    const kingSymbol = turn === 'white' ? 'K' : 'k';
    for (let c = 0; c < 8; c++) {
      for (let r = 0; r < 8; r++) {
        if (state.digital[c]?.[r] === kingSymbol) {
          return getChessCoord(c, r);
        }
      }
    }
    return null;
  }, [state.game?.is_check, state.game?.turn, state.digital, state.status]);

  const handleSquareClick = async (col: number, row: number) => {
    if (state.status !== 'PLAYING') return;

    const clickedCoord = getChessCoord(col, row);

    if (!selectedSquare) {
      const piece = state.digital[col]?.[row];
      if (piece && piece !== '.') {
        const isWhitePiece = piece === piece.toUpperCase();
        const isMyPiece = state.my_color 
          ? (state.my_color === 'white' ? isWhitePiece : !isWhitePiece)
          : true;

        if (isMyPiece) {
          setSelectedSquare({ col, row });
        }
      }
    } else {
      const fromSquare = getChessCoord(selectedSquare.col, selectedSquare.row);
      const toSquare = clickedCoord;

      if (fromSquare === toSquare) {
        setSelectedSquare(null);
        return;
      }

      // Check if moving onto another friendly piece to switch selection
      const targetPiece = state.digital[col]?.[row];
      if (targetPiece && targetPiece !== '.') {
        const isTargetWhite = targetPiece === targetPiece.toUpperCase();
        const isMyTarget = state.my_color 
          ? (state.my_color === 'white' ? isTargetWhite : !isTargetWhite)
          : true;
        if (isMyTarget && !legalDestinations.has(toSquare)) {
          setSelectedSquare({ col, row });
          return;
        }
      }

      // Check for pawn promotion: White pawn reaching rank 8 (col 7) or Black pawn reaching rank 1 (col 0)
      const movingPiece = state.digital[selectedSquare.col]?.[selectedSquare.row];
      const isPawn = movingPiece?.toLowerCase() === 'p';
      const isPromotion = isPawn && ((movingPiece === 'P' && col === 7) || (movingPiece === 'p' && col === 0));

      if (isPromotion && legalDestinations.has(toSquare)) {
        setPendingPromotion({ from: fromSquare, to: toSquare });
        setSelectedSquare(null);
        return;
      }

      setSelectedSquare(null);
      try {
        const res = await makeMove(fromSquare, toSquare);
        if (res.status !== 'success') {
          console.warn("Move rejected:", res.message);
        }
      } catch (err) {
        console.error("Error making move:", err);
      }
    }
  };

  const handleExecutePromotion = async (promotionPiece: string) => {
    if (!pendingPromotion) return;
    const { from, to } = pendingPromotion;
    setPendingPromotion(null);
    try {
      await makeMove(from, to, promotionPiece);
    } catch (err) {
      console.error("Error executing promotion:", err);
    }
  };

  const handleToggleVirtualOnly = async () => {
    const nextMode = !state.virtual_only;
    try {
      await setGameMode(nextMode);
    } catch (err) {
      console.error("Error updating game mode:", err);
    }
  };

  const handleSeek = async () => {
    setLoading(true);
    try {
      await seekGame({
        timeControl: selectedTC,
        rated: isRated,
        color: selectedColor,
        opponent: opponentMode,
        aiLevel: aiLevel,
        ratingRange: computedRatingRange,
      });
    } catch (err) {
      console.error("Error seeking match:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    setLoading(true);
    try {
      await cancelGame();
    } catch (err) {
      console.error("Error cancelling match/seek:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleResign = async () => {
    if (!window.confirm("Are you sure you want to resign the game?")) return;
    setLoading(true);
    try {
      await resignGame();
    } catch (err) {
      console.error("Error resigning game:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleOfferDraw = async () => {
    setLoading(true);
    try {
      await offerDraw(true);
    } catch (err) {
      console.error("Error offering draw:", err);
    } finally {
      setLoading(false);
    }
  };

  // Hardware Debugging & Settings State
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
    pieces_mode?: 'auto' | 'pieces' | 'empty';
  } | null>(null);

  const [positiveThresh, setPositiveThresh] = useState<number>(180);
  const [negativeThresh, setNegativeThresh] = useState<number>(180);
  const [colMode, setColMode] = useState<'auto' | 'manual'>('auto');
  const [manualCol, setManualCol] = useState<number>(0);
  const [scanDelay, setScanDelay] = useState<number>(100);
  const [muxSettleMs, setMuxSettleMs] = useState<number>(10);
  const [debounceThreshold, setDebounceThreshold] = useState<number>(2);
  const [baselineWindowS, setBaselineWindowS] = useState<number>(2);
  const [piecesMode, setPiecesMode] = useState<'auto' | 'pieces' | 'empty'>('auto');
  const [calibrating, setCalibrating] = useState(false);
  const [calibrationStatus, setCalibrationStatus] = useState<string | null>(null);
  const [settingsStatus, setSettingsStatus] = useState<string | null>(null);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await getBoardSettings();
        setSettings(res);
        setPositiveThresh(res.threshold_positive ?? 180);
        setNegativeThresh(res.threshold_negative ?? 180);
        setColMode(res.col_mode || 'auto');
        setManualCol(res.manual_col !== undefined ? res.manual_col : 0);
        setScanDelay(res.scan_delay !== undefined ? res.scan_delay : 100);
        setMuxSettleMs(res.mux_settle_ms !== undefined ? res.mux_settle_ms : 10);
        setDebounceThreshold(res.debounce_threshold !== undefined ? res.debounce_threshold : 2);
        setBaselineWindowS(res.baseline_window_s !== undefined ? res.baseline_window_s : 2);
        setPiecesMode(res.pieces_mode ?? 'auto');
      } catch (err) {
        console.error("Error fetching board settings:", err);
      }
    };
    if (isConnected) {
      fetchSettings();
    }
  }, [isConnected]);

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
      console.error("Error clearing LEDs:", err);
    }
  };

  const handleTriggerAnimation = async (name: string, params?: Record<string, unknown>) => {
    try {
      await triggerAnimation(name, params);
    } catch (err) {
      console.error("Error triggering animation:", err);
    }
  };

  const handleTestTrace = async (uci: string, is_capture: boolean = false) => {
    try {
      await testMoveTrace({ uci, is_capture });
    } catch (err) {
      console.error("Error testing trace:", err);
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
      console.error("Error updating disabled squares:", err);
    }
  };

  const handleCalibrate = async () => {
    setCalibrating(true);
    setCalibrationStatus("Calibrating... Keep board clear");
    try {
      const res = await calibrateBoard();
      if (res.status === 'success') {
        setSettings(res.settings);
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

  const handleCalibrateWithPieces = async () => {
    setCalibrating(true);
    setCalibrationStatus("Calibrating with pieces in place...");
    try {
      const res = await calibrateBoardWithPieces();
      if (res.status === 'success') {
        setSettings(res.settings);
        setCalibrationStatus("Success: Baselines mapped from middle ranks!");
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
        currentDisabled,
        piecesMode
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

  const handleSetPiecesMode = async (newMode: 'auto' | 'pieces' | 'empty') => {
    setPiecesMode(newMode);
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
        currentDisabled,
        newMode
      );
      if (res.status === 'success') {
        setSettings(res.settings);
        setSettingsStatus(`Board mode set to ${newMode.toUpperCase()}`);
      }
    } catch (err) {
      console.error("Error setting pieces mode:", err);
    } finally {
      setTimeout(() => setSettingsStatus(null), 4000);
    }
  };

  const isMyTurn = state.status === 'PLAYING' && state.game?.turn === state.my_color;
  const isOpponentTurn = state.status === 'PLAYING' && !isMyTurn;

  return (
    <div className="min-h-screen w-full bg-slate-950 text-slate-100 flex flex-col font-sans select-none">
      {/* Header / Top Navigation Bar */}
      <header className={`p-3 md:p-4 flex items-center justify-between border-b transition-colors duration-700 ${
        state.status === 'SEEKING' ? 'border-blue-500/40 bg-blue-950/20' :
        state.status === 'PLAYING' ? 'border-emerald-500/40 bg-emerald-950/20' :
        'border-slate-850 bg-slate-900/50'
      }`}>
        <div className="flex items-center gap-3 md:gap-5">
          <div className="flex flex-col text-left">
            <div className="flex items-center gap-2">
              <h1 className="font-extrabold text-base md:text-lg tracking-tight bg-gradient-to-r from-blue-400 to-indigo-300 bg-clip-text text-transparent">
                Smart Chess
              </h1>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-bold uppercase tracking-wider font-mono">
                Lichess Board API
              </span>
            </div>
            <span className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold mt-0.5">
              Status: <span className={
                state.status === 'PLAYING' ? 'text-emerald-400 font-bold' :
                state.status === 'SEEKING' ? 'text-blue-400 font-bold animate-pulse' :
                'text-slate-300 font-bold'
              }>{state.status}</span>
            </span>
          </div>

          {/* Subsystem & Mode Badges */}
          <div className="hidden sm:flex items-center gap-2">
            {/* Lichess Account Badge */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-bold font-mono ${
              account?.authenticated
                ? 'bg-indigo-500/10 text-indigo-300 border-indigo-500/30 shadow-[0_0_8px_rgba(99,102,241,0.15)]'
                : 'bg-slate-900 text-slate-400 border-slate-800'
            }`}>
              <User size={12} className={account?.authenticated ? 'text-indigo-400' : 'text-slate-500'} />
              <span>{account?.authenticated ? `${account.username} (${account.rating})` : 'Lichess: Guest'}</span>
            </div>

            {/* Virtual-Only vs Hardware Mode Switcher */}
            <button
              onClick={handleToggleVirtualOnly}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-bold uppercase tracking-wider font-mono transition-all duration-300 ${
                state.virtual_only
                  ? 'bg-purple-500/20 text-purple-300 border-purple-500/40 shadow-[0_0_10px_rgba(168,85,247,0.2)]'
                  : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:border-emerald-500/40'
              }`}
            >
              <Layers size={12} className={state.virtual_only ? 'text-purple-400' : 'text-emerald-400'} />
              <span>{state.virtual_only ? 'Virtual Only' : 'Hardware Board'}</span>
            </button>

            {/* Server Online Badge */}
            <div className={`flex items-center gap-1 px-2 py-1 rounded-full border text-[9px] font-bold uppercase tracking-wider font-mono ${
              isConnected ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
              {isConnected ? 'Server OK' : 'Offline'}
            </div>
          </div>
        </div>

        {/* Tab & Controls Switcher */}
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800">
            <button 
              onClick={() => setActiveTab('play')}
              className={`px-3 py-1 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
                activeTab === 'play' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              Play
            </button>
            <button 
              onClick={() => setActiveTab('debug')}
              className={`px-3 py-1 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-1.5 ${
                activeTab === 'debug' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Terminal size={12} />
              Debug
            </button>
          </div>
        </div>
      </header>

      {/* Main Content View */}
      {activeTab === 'play' ? (
        <main className="flex-grow p-3 md:p-6 flex flex-col lg:flex-row items-center lg:items-start justify-center gap-6 max-w-6xl mx-auto w-full">
          
          {/* Left / Center Column: 8x8 Chessboard */}
          <div className="w-full max-w-[460px] md:max-w-[520px] flex flex-col flex-shrink-0">
            
            {/* Opponent Header Bar */}
            <div className={`flex justify-between items-center bg-slate-900/80 border border-slate-800 rounded-t-2xl px-4 py-2.5 text-xs transition-all duration-300 ${
              isOpponentTurn ? 'border-amber-500/50 bg-amber-950/10 shadow-[0_0_12px_rgba(245,158,11,0.1)]' : ''
            }`}>
              <div className="flex items-center gap-2.5">
                <div className={`w-3 h-3 rounded-full border ${
                  state.my_color === 'white' ? 'bg-slate-900 border-slate-700' : 'bg-slate-100 border-slate-300'
                }`} />
                <div className="flex flex-col text-left">
                  <span className="font-bold text-slate-200 text-xs flex items-center gap-1.5">
                    {state.game?.opponent?.username || 'Opponent'}
                    {state.game?.opponent?.title && (
                      <span className="text-[9px] bg-amber-500/20 text-amber-300 px-1 py-0.2 rounded font-mono font-bold">
                        {state.game.opponent.title}
                      </span>
                    )}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    Rating: {state.game?.opponent?.rating || 1500}
                  </span>
                </div>
              </div>

              {/* Opponent Clock */}
              <div className={`font-mono text-base font-extrabold px-3 py-1 rounded-lg border transition-all ${
                isOpponentTurn
                  ? 'bg-amber-500/20 border-amber-500/60 text-amber-300 animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.3)]'
                  : 'bg-slate-950 border-slate-800 text-slate-400'
              }`}>
                {state.my_color === 'white' ? (state.clocks?.black || '?:??') : (state.clocks?.white || '?:??')}
              </div>
            </div>

            {/* 8x8 Board Container */}
            <div className="relative w-full aspect-square bg-slate-900 overflow-hidden shadow-2xl border-x-4 border-slate-800">
              <div className="grid grid-cols-8 grid-rows-8 w-full h-full">
                {Array(8).fill(null).map((_, rIdx) => (
                  Array(8).fill(null).map((_, cIdx) => {
                    const isFlipped = state.my_color === 'black';
                    const displayCol = isFlipped ? rIdx : 7 - rIdx;
                    const displayRow = isFlipped ? 7 - cIdx : cIdx;
                    const isDark = (displayCol + displayRow) % 2 === 0;

                    const coord = getChessCoord(displayCol, displayRow);
                    const piece = state.digital[displayCol]?.[displayRow] || '.';
                    const isSelected = selectedSquare?.col === displayCol && selectedSquare?.row === displayRow;
                    const isLegalDest = legalDestinations.has(coord);
                    const isLastMoveSrc = lastMoveSquares?.from === coord;
                    const isLastMoveDst = lastMoveSquares?.to === coord;
                    const isInCheck = kingInCheckCoord === coord;

                    let squareBgClass = isDark ? 'bg-slate-700/80' : 'bg-slate-600/60';
                    if (isLastMoveSrc || isLastMoveDst) {
                      squareBgClass = isDark ? 'bg-amber-700/40' : 'bg-amber-600/40';
                    }

                    return (
                      <div 
                        key={`sq-${displayCol}-${displayRow}`}
                        onClick={() => handleSquareClick(displayCol, displayRow)}
                        className={`flex items-center justify-center relative cursor-pointer select-none transition-colors duration-150 ${squareBgClass} ${
                          isSelected ? 'ring-4 ring-yellow-400 ring-inset bg-yellow-400/30' : ''
                        } ${
                          isInCheck ? 'ring-4 ring-rose-500 ring-inset bg-rose-500/30 animate-pulse' : ''
                        }`}
                      >
                        {/* Piece Icon */}
                        {renderPiece(piece)}

                        {/* Legal Move Indicator Dot */}
                        {isLegalDest && (
                          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                            {piece !== '.' ? (
                              <div className="w-full h-full rounded-none ring-4 ring-emerald-400/80 ring-inset bg-emerald-400/20 animate-pulse" />
                            ) : (
                              <div className="w-3.5 h-3.5 rounded-full bg-emerald-400/80 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
                            )}
                          </div>
                        )}

                        {/* Rank & File labels along edges */}
                        {((!isFlipped && displayRow === 0) || (isFlipped && displayRow === 7)) && (
                          <span className="absolute top-0.5 left-1 text-[8px] font-bold text-slate-400 font-mono opacity-60">
                            {displayCol + 1}
                          </span>
                        )}
                        {((!isFlipped && displayCol === 0) || (isFlipped && displayCol === 7)) && (
                          <span className="absolute bottom-0.5 right-1 text-[8px] font-bold text-slate-400 font-mono opacity-60">
                            {String.fromCharCode(97 + displayRow)}
                          </span>
                        )}
                      </div>
                    );
                  })
                ))}
              </div>

              {/* Physical Sensor Overlay (Visible when not actively playing and not virtual-only) */}
              {state.status !== 'PLAYING' && !state.virtual_only && (
                <div className="absolute inset-0 bg-blue-950/10 border border-blue-500/20 backdrop-blur-[0.5px] z-10 pointer-events-none">
                  <div className="absolute top-1 left-2 bg-blue-600/90 text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider text-white">
                    Physical Sensors Active
                  </div>
                  <div className="grid grid-cols-8 grid-rows-8 w-full h-full p-1 gap-1 pointer-events-auto">
                    {Array(8).fill(null).map((_, rIdx) => (
                      Array(8).fill(null).map((_, cIdx) => {
                        const isFlipped = state.my_color === 'black';
                        const fileIdx = isFlipped ? (7 - cIdx) : cIdx;
                        const rankIdx = isFlipped ? rIdx : (7 - rIdx);

                        const sensorStateVal = state.physical.grid?.[fileIdx]?.[rankIdx] ?? 0;
                        const isHighlighted = state.physical.highlighted_square?.[0] === fileIdx && state.physical.highlighted_square?.[1] === rankIdx;
                        const isDisabled = (state.physical.disabled_squares ?? []).some(
                          (sq) => sq[0] === fileIdx && sq[1] === rankIdx
                        );

                        let bgClass = 'bg-slate-900/30';
                        if (isDisabled) {
                          bgClass = 'bg-slate-950/80 border border-slate-900/40 opacity-25 cursor-not-allowed';
                        } else if (isHighlighted) {
                          bgClass = 'bg-orange-500/80 ring-2 ring-orange-400 shadow-[0_0_8px_rgba(249,115,22,0.6)]';
                        } else if (sensorStateVal === 1) {
                          bgClass = 'bg-red-500/80 shadow-[0_0_8px_rgba(239,68,68,0.6)]';
                        } else if (sensorStateVal === -1) {
                          bgClass = 'bg-emerald-500/80 shadow-[0_0_8px_rgba(16,185,129,0.6)]';
                        }

                        return (
                          <div 
                            key={`sensor-${fileIdx}-${rankIdx}`}
                            onClick={() => {
                              if (!isDisabled) handleToggleHighlight(fileIdx, rankIdx);
                            }}
                            onContextMenu={(e) => {
                              e.preventDefault();
                              handleToggleDisableSquare(fileIdx, rankIdx);
                            }}
                            className={`rounded transition-all duration-200 cursor-pointer ${isDisabled ? '' : 'hover:bg-slate-800/60'} ${bgClass}`}
                          />
                        );
                      })
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Player Footer Bar */}
            <div className={`flex justify-between items-center bg-slate-900/80 border border-slate-800 rounded-b-2xl px-4 py-2.5 text-xs transition-all duration-300 ${
              isMyTurn ? 'border-emerald-500/50 bg-emerald-950/10 shadow-[0_0_12px_rgba(16,185,129,0.1)]' : ''
            }`}>
              <div className="flex items-center gap-2.5">
                <div className={`w-3 h-3 rounded-full border ${
                  state.my_color === 'black' ? 'bg-slate-900 border-slate-700' : 'bg-slate-100 border-slate-300'
                }`} />
                <div className="flex flex-col text-left">
                  <span className="font-bold text-slate-200 text-xs flex items-center gap-1.5">
                    {account?.username || 'You'} (Playing as {state.my_color || 'White'})
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    Rating: {account?.rating || 1500}
                  </span>
                </div>
              </div>

              {/* Player Clock */}
              <div className={`font-mono text-base font-extrabold px-3 py-1 rounded-lg border transition-all ${
                isMyTurn
                  ? 'bg-emerald-500/20 border-emerald-500/60 text-emerald-300 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.3)]'
                  : 'bg-slate-950 border-slate-800 text-slate-400'
              }`}>
                {state.my_color === 'black' ? (state.clocks?.black || '?:??') : (state.clocks?.white || '?:??')}
              </div>
            </div>
          </div>

          {/* Right Column: Game Matchmaking & Controls Panel */}
          <div className="w-full max-w-[460px] md:max-w-md flex flex-col gap-4">
            
            {/* Status & Info Card */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col gap-3 text-left">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-extrabold uppercase tracking-wider text-slate-400">
                  Game Controls & Status
                </h2>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                  state.status === 'PLAYING' ? 'bg-emerald-500/20 text-emerald-300' :
                  state.status === 'SEEKING' ? 'bg-blue-500/20 text-blue-300 animate-pulse' :
                  'bg-slate-800 text-slate-400'
                }`}>
                  {state.status}
                </span>
              </div>

              {/* Seeking Notification */}
              {state.status === 'SEEKING' && (
                <div className="bg-blue-900/30 border border-blue-500/40 rounded-xl p-3 flex items-center gap-3 animate-pulse">
                  <RefreshCw className="text-blue-400 animate-spin flex-shrink-0" size={20} />
                  <div className="flex flex-col">
                    <span className="text-xs font-bold text-blue-200">
                      {opponentMode === 'ai' || selectedTC.startsWith('1+') || selectedTC.startsWith('3+') || selectedTC.startsWith('5+')
                        ? 'Initiating match against Stockfish AI...'
                        : 'Seeking Live Match on Lichess...'}
                    </span>
                    <span className="text-[10px] text-blue-300/80 font-mono">
                      {selectedTC} • {isRated ? 'Rated' : 'Casual'} • {selectedColor}
                    </span>
                  </div>
                </div>
              )}

              {/* Match Playing Info */}
              {state.status === 'PLAYING' && (
                <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-xl p-3 flex flex-col gap-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-slate-400">Game ID:</span>
                    <span className="font-mono text-emerald-400 font-bold">{state.game?.game_id || 'Active'}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-slate-400">Turn:</span>
                    <span className="font-bold uppercase text-white">{state.game?.turn}</span>
                  </div>
                  {state.game?.is_check && (
                    <div className="bg-rose-500/20 text-rose-300 border border-rose-500/40 text-xs px-2.5 py-1 rounded font-bold text-center animate-pulse">
                      ⚠️ CHECK!
                    </div>
                  )}
                </div>
              )}

              {/* Game Over Info */}
              {(state.status === 'GAME_OVER' || state.game?.is_game_over) && (
                <div className="bg-purple-950/40 border border-purple-500/40 rounded-xl p-3 flex flex-col items-center gap-1 text-center">
                  <CheckCircle2 className="text-purple-400" size={24} />
                  <span className="font-bold text-sm text-purple-200">Game Concluded</span>
                  <span className="text-xs text-purple-300/80 font-mono">
                    Winner: {state.game?.winner ? state.game.winner.toUpperCase() : 'Draw'} ({state.game?.end_reason || 'Finished'})
                  </span>
                </div>
              )}
            </div>

            {/* Matchmaking Selection Controls (When IDLE or GAME_OVER) */}
            {(state.status === 'IDLE' || state.status === 'GAME_OVER') && (
              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col gap-4 text-left">
                
                {/* Lichess Board API Guidance Banner */}
                <div className="bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-3 flex items-start gap-2.5">
                  <Zap className="text-amber-400 flex-shrink-0 mt-0.5" size={16} />
                  <p className="text-[11px] text-indigo-200 leading-snug">
                    <strong className="text-white">Smart Matchmaking:</strong> Fast matches under 8 min (<span className="text-amber-300 font-mono">Bullet &amp; Blitz</span>) play instantly against <span className="text-amber-300 font-semibold">Stockfish AI</span>. For live human matchmaking on the Board API, select <span className="text-emerald-300 font-mono">Rapid (10+0 or 15+10)</span>.
                  </p>
                </div>

                {/* Time Control Buttons */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Select Time Control
                  </label>
                  <div className="grid grid-cols-4 gap-1.5">
                    {[
                      { id: '1+0', label: '1+0', sub: 'Bullet' },
                      { id: '3+0', label: '3+0', sub: 'Blitz' },
                      { id: '3+2', label: '3+2', sub: 'Blitz' },
                      { id: '5+0', label: '5+0', sub: 'Blitz' },
                      { id: '5+3', label: '5+3', sub: 'Blitz' },
                      { id: '10+0', label: '10+0', sub: 'Rapid' },
                      { id: '15+10', label: '15+10', sub: 'Rapid' },
                      { id: '30+0', label: '30+0', sub: 'Classical' },
                    ].map((tc) => (
                      <button
                        key={tc.id}
                        disabled={loading || !isConnected}
                        onClick={() => setSelectedTC(tc.id)}
                        className={`flex flex-col items-center justify-center p-2 rounded-xl border transition-all ${
                          selectedTC === tc.id
                            ? 'bg-blue-600 border-blue-400 text-white shadow-md shadow-blue-900/20'
                            : 'bg-slate-950 hover:bg-slate-850 border-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        <span className="text-xs font-bold font-mono">{tc.label}</span>
                        <span className="text-[8px] uppercase tracking-wider opacity-70">{tc.sub}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Opponent Mode & AI Level */}
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Opponent Mode
                    </label>
                    <div className="grid grid-cols-3 gap-1">
                      {[
                        { id: 'auto', label: 'Auto' },
                        { id: 'ai', label: 'AI' },
                        { id: 'human', label: 'Human' },
                      ].map((mode) => (
                        <button
                          key={mode.id}
                          onClick={() => setOpponentMode(mode.id as 'auto' | 'ai' | 'human')}
                          className={`py-1.5 text-[11px] font-bold rounded-lg border transition-all ${
                            opponentMode === mode.id
                              ? 'bg-blue-600 border-blue-400 text-white shadow-sm'
                              : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'
                          }`}
                        >
                          {mode.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* AI Difficulty Level (Active for AI / Auto fast matches) */}
                  <div className="flex flex-col gap-1.5">
                    <div className="flex justify-between items-center text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      <span className="flex items-center gap-1">
                        <Bot size={12} className="text-indigo-400" />
                        AI Level
                      </span>
                      <span className="font-mono text-indigo-300 font-bold">Lvl {aiLevel}</span>
                    </div>
                    <div className="grid grid-cols-4 gap-1">
                      {[1, 3, 5, 8].map((lvl) => (
                        <button
                          key={lvl}
                          onClick={() => setAiLevel(lvl)}
                          className={`py-1.5 text-[10px] font-bold rounded-lg border transition-all ${
                            aiLevel === lvl
                              ? 'bg-indigo-600 border-indigo-400 text-white'
                              : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'
                          }`}
                        >
                          {lvl === 1 ? '1' : lvl === 3 ? '3' : lvl === 5 ? '5' : '8 (Max)'}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Color & Rated Options */}
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Play As
                    </label>
                    <div className="grid grid-cols-3 gap-1">
                      {(['random', 'white', 'black'] as const).map((c) => (
                        <button
                          key={c}
                          onClick={() => setSelectedColor(c)}
                          className={`py-1.5 text-xs font-bold rounded-lg border capitalize transition-all ${
                            selectedColor === c
                              ? 'bg-indigo-600 border-indigo-400 text-white shadow-sm'
                              : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'
                          }`}
                        >
                          {c}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="flex flex-col gap-1.5 justify-end">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Match Rating
                    </label>
                    <button
                      onClick={() => setIsRated(!isRated)}
                      className={`py-1.5 px-3 rounded-lg border text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                        isRated
                          ? 'bg-amber-600/20 text-amber-300 border-amber-500/50 shadow-sm'
                          : 'bg-slate-950 text-slate-400 border-slate-800'
                      }`}
                    >
                      <Shield size={13} className={isRated ? 'text-amber-400' : 'text-slate-500'} />
                      <span>{isRated ? 'Rated (Fast Auto-Match)' : 'Casual (Open Challenge)'}</span>
                    </button>
                  </div>
                </div>

                {/* Rating Guidance Note */}
                {!isRated && opponentMode !== 'ai' && (
                  <div className="text-[10px] text-amber-300/80 bg-amber-950/20 border border-amber-500/20 px-2.5 py-1.5 rounded-lg flex items-center gap-1.5">
                    <span>💡 <strong>Note:</strong> Lichess Quick Pairing pool is exclusively for Rated games. Casual/Unrated seeks post to the public lobby where few players search.</span>
                  </div>
                )}

                {/* Rating Boundaries (ELO Interval) */}
                <div className="flex flex-col gap-2 pt-1 border-t border-slate-800/80">
                  <div className="flex justify-between items-center">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <Target size={12} className="text-amber-400" />
                      ELO Rating Boundaries
                    </label>
                    <span className="text-[10px] text-amber-300/90 font-mono font-semibold">
                      {ratingBoundary === 'any' ? 'Any Rating (Default)' : computedRatingRange ? `${computedRatingRange} ELO` : 'Custom'}
                    </span>
                  </div>

                  <div className="grid grid-cols-6 gap-1">
                    {[
                      { id: 'any', label: 'Any' },
                      { id: '100', label: '±100' },
                      { id: '200', label: '±200' },
                      { id: '300', label: '±300' },
                      { id: '500', label: '±500' },
                      { id: 'custom', label: 'Custom' },
                    ].map((boundary) => (
                      <button
                        key={boundary.id}
                        onClick={() => setRatingBoundary(boundary.id as typeof ratingBoundary)}
                        className={`py-1.5 text-[10px] font-bold rounded-lg border transition-all ${
                          ratingBoundary === boundary.id
                            ? 'bg-amber-600/30 border-amber-400 text-amber-200 shadow-sm'
                            : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        {boundary.label}
                      </button>
                    ))}
                  </div>

                  {ratingBoundary === 'custom' && (
                    <div className="grid grid-cols-2 gap-2 pt-1">
                      <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-lg px-2 py-1">
                        <span className="text-[10px] text-slate-500 font-bold uppercase">Min:</span>
                        <input
                          type="number"
                          value={customMinRating}
                          onChange={(e) => setCustomMinRating(e.target.value)}
                          className="w-full bg-transparent text-xs font-mono font-bold text-slate-200 outline-none"
                          placeholder="800"
                        />
                      </div>
                      <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-lg px-2 py-1">
                        <span className="text-[10px] text-slate-500 font-bold uppercase">Max:</span>
                        <input
                          type="number"
                          value={customMaxRating}
                          onChange={(e) => setCustomMaxRating(e.target.value)}
                          className="w-full bg-transparent text-xs font-mono font-bold text-slate-200 outline-none"
                          placeholder="2500"
                        />
                      </div>
                    </div>
                  )}

                  <p className="text-[9px] text-slate-500 leading-tight">
                    {ratingBoundary === 'any'
                      ? 'Default: Unrestricted matching on Lichess (matches with any active player).'
                      : `Only seeks human opponents within ${computedRatingRange || 'custom range'} ELO on Lichess.`}
                  </p>
                </div>

                {/* Seek / Start Match Button */}
                <button
                  onClick={handleSeek}
                  disabled={loading || !isConnected}
                  className="w-full mt-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-extrabold text-base py-3.5 rounded-xl shadow-lg shadow-blue-900/30 flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
                >
                  <Play size={18} fill="currentColor" />
                  <span>Start Match ({selectedTC})</span>
                </button>
              </div>
            )}

            {/* In-Game Action Buttons */}
            {state.status === 'SEEKING' && (
              <button
                onClick={handleCancel}
                disabled={loading}
                className="w-full bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 py-3.5 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all"
              >
                <XCircle size={18} />
                <span>Cancel Match Search</span>
              </button>
            )}

            {state.status === 'PLAYING' && (
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={handleResign}
                  disabled={loading}
                  className="bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 py-3 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all"
                >
                  <Flag size={16} />
                  <span>Resign Game</span>
                </button>
                <button
                  onClick={handleOfferDraw}
                  disabled={loading}
                  className="bg-slate-900 hover:bg-slate-850 text-slate-300 border border-slate-800 py-3 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all"
                >
                  <Handshake size={16} />
                  <span>Offer Draw</span>
                </button>
              </div>
            )}
          </div>
        </main>
      ) : (
        /* Debug / Hardware Diagnostics Tab */
        <main className="flex-grow p-4 md:p-8 flex flex-col lg:flex-row items-center lg:items-start justify-center gap-6 max-w-6xl mx-auto w-full">
          {/* Diagnostic 8x8 Grid */}
          <div className="w-full max-w-2xl flex-shrink-0 bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="text-blue-400" size={22} />
                <h2 className="text-base font-bold">Physical ADC Sensor Matrix</h2>
              </div>
              <span className="font-mono text-xs text-blue-400 font-bold bg-slate-950 px-2.5 py-1 rounded border border-slate-850">
                Thresholds: +{positiveThresh} / -{negativeThresh}
              </span>
            </div>

            <div className="grid grid-cols-8 gap-1.5 w-full">
              {Array(8).fill(null).map((_, rIdx) => (
                Array(8).fill(null).map((_, cIdx) => {
                  const sensorRank = 7 - rIdx;
                  const sensorFile = cIdx;
                  const rawAdc = state.physical.adc?.[sensorFile]?.[sensorRank] ?? 0;
                  const sensorStateVal = state.physical.grid?.[sensorFile]?.[sensorRank] ?? 0;
                  const baseline = state.physical.baselines?.[sensorFile]?.[sensorRank] ?? settings?.baselines?.[sensorFile]?.[sensorRank] ?? 1550;
                  const diffVal = rawAdc - baseline;

                  const file = String.fromCharCode(97 + sensorFile);
                  const rank = sensorRank + 1;
                  const chessCoord = `${file}${rank}`;

                  const isColActive = colMode === 'auto' || sensorFile === manualCol;
                  const isHighlighted = state.physical.highlighted_square?.[0] === sensorFile && state.physical.highlighted_square?.[1] === sensorRank;
                  const isDisabled = (state.physical.disabled_squares ?? []).some(
                    (sq) => sq[0] === sensorFile && sq[1] === sensorRank
                  );

                  let cardClass = 'bg-slate-950 border-slate-850 text-slate-300';
                  let statusText = 'IDLE';
                  let statusColor = 'text-slate-600';

                  if (isDisabled) {
                    cardClass = 'bg-slate-950/20 border-slate-900/40 text-slate-600 opacity-40 line-through';
                    statusText = 'OFF';
                  } else if (isHighlighted) {
                    cardClass = 'bg-orange-950/40 border-orange-500/80 ring-2 ring-orange-500/40 text-orange-200';
                    statusText = 'LIGHT';
                    statusColor = 'text-orange-400';
                  } else if (sensorStateVal === 1) {
                    cardClass = 'bg-red-950/40 border-red-500/80 text-red-200';
                    statusText = 'NORTH';
                    statusColor = 'text-red-400';
                  } else if (sensorStateVal === -1) {
                    cardClass = 'bg-emerald-950/40 border-emerald-500/80 text-emerald-200';
                    statusText = 'SOUTH';
                    statusColor = 'text-emerald-400';
                  }

                  return (
                    <div 
                      key={`dbg-${sensorFile}-${sensorRank}`}
                      onClick={() => !isDisabled && handleToggleHighlight(sensorFile, sensorRank)}
                      onContextMenu={(e) => {
                        e.preventDefault();
                        handleToggleDisableSquare(sensorFile, sensorRank);
                      }}
                      className={`flex flex-col justify-between p-1 rounded-lg border transition-all cursor-pointer ${cardClass} ${
                        isColActive ? 'opacity-100' : 'opacity-25'
                      }`}
                    >
                      <div className="flex justify-between items-center text-[8px] font-mono text-slate-500">
                        <span>{chessCoord}</span>
                        <span>[{sensorFile},{sensorRank}]</span>
                      </div>
                      <div className="text-center my-0.5">
                        <span className="text-xs font-extrabold font-mono block">
                          {diffVal > 0 ? `+${diffVal}` : diffVal}
                        </span>
                        <span className="text-[7px] text-slate-500 font-mono block">
                          B:{baseline}
                        </span>
                      </div>
                      <span className={`text-[7px] font-bold uppercase ${statusColor}`}>
                        {statusText}
                      </span>
                    </div>
                  );
                })
              ))}
            </div>
          </div>

          {/* Debug Controls & Tools */}
          <div className="w-full max-w-md flex flex-col gap-4 text-left">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Sliders size={14} className="text-blue-400" />
                Calibration & Hardware Utilities
              </h3>

              {/* Threshold Sliders */}
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-400">Positive Shift (+)</span>
                    <span className="font-mono text-red-400 font-bold">+{positiveThresh}</span>
                  </div>
                  <input 
                    type="range"
                    min="10"
                    max="1000"
                    step="10"
                    value={positiveThresh}
                    onChange={(e) => setPositiveThresh(parseInt(e.target.value))}
                    className="w-full h-1 bg-slate-950 rounded appearance-none cursor-pointer accent-red-500"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-400">Negative Shift (-)</span>
                    <span className="font-mono text-emerald-400 font-bold">-{negativeThresh}</span>
                  </div>
                  <input 
                    type="range"
                    min="10"
                    max="1000"
                    step="10"
                    value={negativeThresh}
                    onChange={(e) => setNegativeThresh(parseInt(e.target.value))}
                    className="w-full h-1 bg-slate-950 rounded appearance-none cursor-pointer accent-emerald-500"
                  />
                </div>

                <button
                  onClick={handleSaveThresholds}
                  className="w-full bg-slate-950 hover:bg-slate-850 border border-slate-800 py-2 rounded-xl text-xs font-bold uppercase tracking-wider transition-all"
                >
                  Save Thresholds
                </button>
                {settingsStatus && (
                  <span className="text-[10px] text-blue-400 font-mono text-center font-bold">{settingsStatus}</span>
                )}

                <hr className="border-slate-800/80 my-1" />

                {/* Smart Pieces Detection Status & Mode Switch */}
                <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3 flex flex-col gap-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wide">
                      Initial Pieces Detection
                    </span>
                    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                      state.physical.effective_pieces_mode
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        : 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                    }`}>
                      {state.physical.effective_pieces_mode
                        ? `Pieces Present (${state.physical.detected_starting_count ?? 0}/32)`
                        : `Empty Board (${state.physical.detected_starting_count ?? 0}/32)`}
                    </span>
                  </div>

                  <div className="text-[10px] text-slate-400 leading-tight">
                    {state.physical.effective_pieces_mode
                      ? 'In-loop baseline calibration active on middle ranks (propagating to ranks 1-2 & 7-8).'
                      : 'In-loop baseline calibration active on all 64 squares directly.'}
                  </div>

                  {/* 3-Way Mode Switch */}
                  <div className="grid grid-cols-3 gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800">
                    <button
                      type="button"
                      onClick={() => handleSetPiecesMode('auto')}
                      className={`py-1.5 px-2 text-[10px] font-bold uppercase tracking-wider rounded-md transition-all ${
                        piecesMode === 'auto'
                          ? 'bg-blue-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                      }`}
                    >
                      Auto (Smart)
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSetPiecesMode('pieces')}
                      className={`py-1.5 px-2 text-[10px] font-bold uppercase tracking-wider rounded-md transition-all ${
                        piecesMode === 'pieces'
                          ? 'bg-emerald-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                      }`}
                    >
                      Pieces Placed
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSetPiecesMode('empty')}
                      className={`py-1.5 px-2 text-[10px] font-bold uppercase tracking-wider rounded-md transition-all ${
                        piecesMode === 'empty'
                          ? 'bg-amber-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                      }`}
                    >
                      Empty Board
                    </button>
                  </div>
                </div>

                <hr className="border-slate-800/80 my-1" />

                {/* Calibrate with Pieces Placed */}
                <button
                  onClick={handleCalibrateWithPieces}
                  disabled={calibrating || !isConnected}
                  className="w-full bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all"
                >
                  <RefreshCw size={13} className={calibrating ? 'animate-spin' : ''} />
                  <span>{calibrating ? 'Calibrating...' : 'Calibrate (Pieces Placed)'}</span>
                </button>

                {/* Recalibrate Empty Board */}
                <button
                  onClick={handleCalibrate}
                  disabled={calibrating || !isConnected}
                  className="w-full bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all"
                >
                  <RefreshCw size={13} className={calibrating ? 'animate-spin' : ''} />
                  <span>{calibrating ? 'Recalibrating...' : 'Force Recalibrate (Empty Board)'}</span>
                </button>
                {calibrationStatus && (
                  <span className="text-[10px] text-emerald-400 font-mono text-center font-bold">{calibrationStatus}</span>
                )}

                {/* Diagnostic LED Test */}
                <button
                  onClick={handleTestLeds}
                  disabled={!isConnected || state.physical.led_test_active}
                  className="w-full bg-orange-600/20 hover:bg-orange-600/30 text-orange-300 border border-orange-500/30 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all"
                >
                  <Activity size={13} />
                  <span>Diagnostic LED Test</span>
                </button>

                {/* Clear All LEDs */}
                <button
                  onClick={handleClearLeds}
                  disabled={!isConnected}
                  className="w-full bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/30 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all"
                >
                  <PowerOff size={13} />
                  <span>Force All LEDs Off</span>
                </button>

                <hr className="border-slate-800/80 my-1" />

                {/* LED Animations & Trace Testing */}
                <div className="flex flex-col gap-2 bg-slate-950 p-3 rounded-xl border border-slate-850 text-left">
                  <div className="flex items-center gap-2 text-indigo-400">
                    <Sparkles size={14} />
                    <span className="text-xs font-bold uppercase tracking-wider">Animation & Trace Tests</span>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5 mt-1">
                    <button
                      onClick={() => handleTriggerAnimation('GAME_STARTED')}
                      disabled={!isConnected}
                      className="bg-emerald-950/40 hover:bg-emerald-900/50 border border-emerald-500/30 text-emerald-300 py-1.5 px-2 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1 transition-all"
                    >
                      <Zap size={11} />
                      <span>Start Anim</span>
                    </button>
                    <button
                      onClick={() => handleTriggerAnimation('GAME_WON')}
                      disabled={!isConnected}
                      className="bg-yellow-950/40 hover:bg-yellow-900/50 border border-yellow-500/30 text-yellow-300 py-1.5 px-2 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1 transition-all"
                    >
                      <Sparkles size={11} />
                      <span>Victory (Win)</span>
                    </button>
                    <button
                      onClick={() => handleTriggerAnimation('GAME_LOST')}
                      disabled={!isConnected}
                      className="bg-rose-950/40 hover:bg-rose-900/50 border border-rose-500/30 text-rose-300 py-1.5 px-2 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1 transition-all"
                    >
                      <Flag size={11} />
                      <span>Defeat (Loss)</span>
                    </button>
                    <button
                      onClick={() => handleTriggerAnimation('GAME_DRAWN')}
                      disabled={!isConnected}
                      className="bg-blue-950/40 hover:bg-blue-900/50 border border-blue-500/30 text-blue-300 py-1.5 px-2 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1 transition-all"
                    >
                      <Handshake size={11} />
                      <span>Draw Anim</span>
                    </button>
                  </div>

                  {/* Move Trajectory Trace Tests */}
                  <div className="flex items-center gap-1 mt-1.5 text-[9px] text-slate-400 font-bold uppercase tracking-wider">
                    <Wand2 size={10} />
                    <span>Move Trace Samples:</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <button
                      onClick={() => handleTestTrace('a1h8')}
                      disabled={!isConnected}
                      className="bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-750 py-1.5 px-2 rounded text-[10px] font-mono font-bold flex items-center justify-center gap-1"
                    >
                      <span>a1 ↗ h8 (Diagonal)</span>
                    </button>
                    <button
                      onClick={() => handleTestTrace('g1f3')}
                      disabled={!isConnected}
                      className="bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-750 py-1.5 px-2 rounded text-[10px] font-mono font-bold flex items-center justify-center gap-1"
                    >
                      <span>g1 ♞ f3 (Knight)</span>
                    </button>
                    <button
                      onClick={() => handleTestTrace('e2e4')}
                      disabled={!isConnected}
                      className="bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-750 py-1.5 px-2 rounded text-[10px] font-mono font-bold flex items-center justify-center gap-1"
                    >
                      <span>e2 ↑ e4 (Quiet)</span>
                    </button>
                    <button
                      onClick={() => handleTestTrace('d4e5', true)}
                      disabled={!isConnected}
                      className="bg-rose-950/40 hover:bg-rose-900/50 text-rose-300 border border-rose-500/40 py-1.5 px-2 rounded text-[10px] font-mono font-bold flex items-center justify-center gap-1 shadow-sm"
                    >
                      <span>d4 ⚔ e5 (Capture)</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      )}

      {/* Pawn Promotion Modal Dialog */}
      {pendingPromotion && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div className="bg-slate-900 border-2 border-yellow-500/50 rounded-2xl p-6 shadow-2xl max-w-sm w-full flex flex-col items-center gap-4 text-center">
            <h3 className="font-extrabold text-lg text-yellow-400">Pawn Promotion</h3>
            <p className="text-xs text-slate-300">Choose a piece to promote your pawn:</p>
            
            <div className="grid grid-cols-4 gap-3 w-full my-2">
              {[
                { type: 'q', label: 'Queen', icon: '♕' },
                { type: 'r', label: 'Rook', icon: '♖' },
                { type: 'b', label: 'Bishop', icon: '♗' },
                { type: 'n', label: 'Knight', icon: '♘' },
              ].map((p) => (
                <button
                  key={p.type}
                  onClick={() => handleExecutePromotion(p.type)}
                  className="flex flex-col items-center justify-center p-3 rounded-xl bg-slate-950 border border-slate-800 hover:border-yellow-400 hover:bg-yellow-500/10 text-slate-100 transition-all hover:scale-105"
                >
                  <span className="text-3xl select-none">{p.icon}</span>
                  <span className="text-[10px] font-bold mt-1 text-slate-400">{p.label}</span>
                </button>
              ))}
            </div>

            <button
              onClick={() => setPendingPromotion(null)}
              className="text-xs text-slate-400 hover:text-white underline mt-1"
            >
              Cancel Move
            </button>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="p-3 text-center border-t border-slate-900 text-[10px] text-slate-500 font-mono">
        Smart Chess Board • Lichess Integration v2.0 • Raspberry Pi 4B
      </footer>
    </div>
  )
}

export default App
