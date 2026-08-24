import { useState, useEffect, useMemo, useRef, lazy, Suspense } from 'react'
import { useBoardState } from './hooks/useBoardState'
import { 
  seekGame, 
  cancelGame, 
  resignGame,
  claimVictory,
  offerDraw,
  getLichessAccount,
  getLastGameParams,
  restartPreviousGame,
  setGameMode,
  getBoardSettings, 
  updateBoardSettings, 
  calibrateBoard,
  calibrateBoardWithPieces,
  makeMove,
  calibrateSquare,
  testLeds,
  clearAllLeds,
  triggerAnimation,
  testMoveTrace,
  saveBoardDefaults,
  startAnalysis,
  stopAnalysis,
  resetAnalysisBranch,
  resolvePromotion,
} from './api'
import type { LichessAccount, LastGameParams, BoardSettings } from './api'
import { 
  Play, 
  XCircle, 
  Flag,
  Handshake,
  AlertTriangle,
  Trophy,
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
  Wand2,
  Radar,
  RotateCcw,
  BookmarkCheck,
  Sun,
  Moon,
  Compass,
  Crown,
  BookOpen,
} from 'lucide-react'
const AnalysisTab = lazy(() => import('./components/AnalysisTab'))

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
  const [activeTab, setActiveTab] = useState<'play' | 'analysis' | 'debug'>('play');

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
  const [lastGameParams, setLastGameParams] = useState<LastGameParams | null>(null);

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

  // Disconnection & Victory Claiming State
  const [isClaiming, setIsClaiming] = useState<boolean>(false);

  const opponentGone = state.game?.opponent_gone?.gone ?? false;
  const claimWinIn = state.game?.opponent_gone?.claim_win_in ?? 0;

  // Derived directly from the server-driven countdown so there is a single source of truth
  const claimCountdown = opponentGone ? Math.max(0, Math.ceil(claimWinIn)) : 0;

  const handleClaimVictory = async () => {
    setIsClaiming(true);
    try {
      await claimVictory();
    } catch (err) {
      console.error("Error claiming victory:", err);
    } finally {
      setIsClaiming(false);
    }
  };

  // Fetch Lichess Account & Last Game Params on mount and connection changes
  useEffect(() => {
    if (!isConnected) return;
    let cancelled = false;

    const fetchAccount = async () => {
      try {
        const data = await getLichessAccount();
        if (!cancelled) setAccount(data);
      } catch (err) {
        console.warn("Could not fetch Lichess account:", err);
      }
    };

    const fetchLastParams = async () => {
      try {
        const res = await getLastGameParams();
        if (!cancelled && res.status === 'success' && res.last_game_params) {
          setLastGameParams(res.last_game_params);
        }
      } catch (err) {
        console.warn("Could not fetch last game params:", err);
      }
    };

    fetchAccount();
    fetchLastParams();
    return () => {
      cancelled = true;
    };
  }, [isConnected]);

  useEffect(() => {
    if (!isConnected) return;
    if (state.status !== 'IDLE' && state.status !== 'GAME_OVER' && state.status !== 'PLAYING') return;
    let cancelled = false;
    (async () => {
      try {
        const res = await getLastGameParams();
        if (!cancelled && res.status === 'success' && res.last_game_params) {
          setLastGameParams(res.last_game_params);
        }
      } catch (err) {
        console.warn("Could not fetch last game params:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isConnected, state.status]);

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

  // Map of destination coordinate -> move quality tier for the active selected piece or physical lifted piece
  const destQualities = useMemo(() => {
    const map = new Map<string, 'best' | 'good' | 'inaccuracy' | 'blunder'>();
    if (!state.coach?.enabled || !state.coach?.lifted_move_hints) return map;
    for (const hint of state.coach.lifted_move_hints) {
      const toCoord = hint.uci.slice(2, 4);
      map.set(toCoord, hint.tier);
    }
    return map;
  }, [state.coach]);

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

  // Physical file/rank index (0..7, 0..7) to chess square string (e.g. [4, 3] -> "e4")
  const fileRankToChessCoord = (c: number, r: number): string => {
    return `${String.fromCharCode(97 + c)}${r + 1}`;
  };

  // Guardrail missing piece squares
  const guardrailMissingCoords = useMemo(() => {
    const coords = new Set<string>();
    if (state.physical?.guardrail?.missing_pieces) {
      for (const [c, r] of state.physical.guardrail.missing_pieces) {
        coords.add(fileRankToChessCoord(c, r));
      }
    }
    return coords;
  }, [state.physical?.guardrail?.missing_pieces]);

  // Guardrail unexpected piece squares
  const guardrailUnexpectedCoords = useMemo(() => {
    const coords = new Set<string>();
    if (state.physical?.guardrail?.unexpected_pieces) {
      for (const [c, r] of state.physical.guardrail.unexpected_pieces) {
        coords.add(fileRankToChessCoord(c, r));
      }
    }
    return coords;
  }, [state.physical?.guardrail?.unexpected_pieces]);

  // Capture target lifted first coordinate
  const pendingCaptureTargetCoord = useMemo(() => {
    if (state.physical?.pending_capture_target) {
      const [c, r] = state.physical.pending_capture_target;
      return fileRankToChessCoord(c, r);
    }
    return null;
  }, [state.physical?.pending_capture_target]);

  // Candidate attacker coordinates for in-progress capture
  const candidateAttackerCoords = useMemo(() => {
    const coords = new Set<string>();
    if (state.physical?.capture_candidate_attackers) {
      for (const [c, r] of state.physical.capture_candidate_attackers) {
        coords.add(fileRankToChessCoord(c, r));
      }
    }
    return coords;
  }, [state.physical?.capture_candidate_attackers]);

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

  const handleRestartPrevious = async () => {
    setLoading(true);
    try {
      await restartPreviousGame();
    } catch (err) {
      console.error("Error restarting previous game:", err);
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
  const [settings, setSettings] = useState<BoardSettings | null>(null);

  const [positiveThresh, setPositiveThresh] = useState<number>(() => {
    const saved = localStorage.getItem('scb_positive_thresh');
    return saved ? parseInt(saved, 10) || 200 : 200;
  });
  const [negativeThresh, setNegativeThresh] = useState<number>(() => {
    const saved = localStorage.getItem('scb_negative_thresh');
    return saved ? parseInt(saved, 10) || 200 : 200;
  });
  const [colMode, setColMode] = useState<'auto' | 'manual'>(() => {
    return (localStorage.getItem('scb_col_mode') as 'auto' | 'manual') || 'auto';
  });
  const [manualCol, setManualCol] = useState<number>(() => {
    const saved = localStorage.getItem('scb_manual_col');
    return saved !== null ? parseInt(saved, 10) : 0;
  });
  const [scanDelay, setScanDelay] = useState<number>(() => {
    const saved = localStorage.getItem('scb_scan_delay');
    return saved ? parseInt(saved, 10) : 100;
  });
  const [muxSettleMs, setMuxSettleMs] = useState<number>(() => {
    const saved = localStorage.getItem('scb_mux_settle_ms');
    return saved ? parseInt(saved, 10) : 10;
  });
  const [debounceThreshold, setDebounceThreshold] = useState<number>(() => {
    const saved = localStorage.getItem('scb_debounce_threshold');
    return saved ? parseInt(saved, 10) : 2;
  });
  const [baselineWindowS, setBaselineWindowS] = useState<number>(() => {
    const saved = localStorage.getItem('scb_baseline_window_s');
    return saved ? parseInt(saved, 10) : 2;
  });
  const [piecesMode, setPiecesMode] = useState<'auto' | 'pieces' | 'empty'>(() => {
    return (localStorage.getItem('scb_pieces_mode') as 'auto' | 'pieces' | 'empty') || 'auto';
  });
  const [coachHintsEnabled, setCoachHintsEnabled] = useState<boolean>(() => {
    const saved = localStorage.getItem('scb_coach_hints_enabled');
    return saved !== null ? saved === 'true' : true;
  });
  const [evalBarEnabled, setEvalBarEnabled] = useState<boolean>(() => {
    const saved = localStorage.getItem('scb_eval_bar_enabled');
    return saved !== null ? saved === 'true' : true;
  });
  const [openingHintsEnabled, setOpeningHintsEnabled] = useState<boolean>(() => {
    const saved = localStorage.getItem('scb_opening_hints_enabled');
    return saved !== null ? saved === 'true' : true;
  });
  const [coachAiOnly, setCoachAiOnly] = useState<boolean>(() => {
    const saved = localStorage.getItem('scb_coach_ai_only');
    return saved !== null ? saved === 'true' : true;
  });
  const [inLoopCalibration, setInLoopCalibration] = useState<boolean>(() => {
    const saved = localStorage.getItem('scb_in_loop_calibration');
    return saved !== null ? saved === 'true' : true;
  });
  const [ledIntensity, setLedIntensity] = useState<number>(() => {
    const saved = localStorage.getItem('scb_led_intensity');
    return saved ? parseInt(saved, 10) || 100 : 100;
  });
  const [nightMode, setNightMode] = useState<boolean>(() => {
    const saved = localStorage.getItem('scb_night_mode');
    return saved !== null ? saved === 'true' : false;
  });
  const [calibrating, setCalibrating] = useState(false);
  const [calibrationStatus, setCalibrationStatus] = useState<string | null>(null);
  const [settingsStatus, setSettingsStatus] = useState<string | null>(null);
  const [savingDefaults, setSavingDefaults] = useState(false);
  const [saveDefaultsStatus, setSaveDefaultsStatus] = useState<string | null>(null);

  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Live mirror of the WS state so debounced callbacks never read stale closures
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // Single source of truth for the board-settings payload sent by every save path
  const buildSettingsPayload = (overrides?: {
    pos?: number;
    neg?: number;
    mode?: 'auto' | 'manual';
    col?: number;
    delay?: number;
    settle?: number;
    debounce?: number;
    window_s?: number;
    pMode?: 'auto' | 'pieces' | 'empty';
    coachHints?: boolean;
    evalBar?: boolean;
    openingHints?: boolean;
    aiOnly?: boolean;
    inLoopCal?: boolean;
    intensity?: number;
    nMode?: boolean;
    disabledSquares?: number[][];
  }) => ({
    threshold_positive: overrides?.pos ?? positiveThresh,
    threshold_negative: overrides?.neg ?? negativeThresh,
    col_mode: overrides?.mode ?? colMode,
    manual_col: overrides?.col ?? manualCol,
    scan_delay: overrides?.delay ?? scanDelay,
    mux_settle_us: overrides?.settle ?? muxSettleMs,
    debounce_threshold: overrides?.debounce ?? debounceThreshold,
    baseline_window_s: overrides?.window_s ?? baselineWindowS,
    disabled_squares: overrides?.disabledSquares ?? stateRef.current.physical.disabled_squares ?? [],
    pieces_mode: overrides?.pMode ?? piecesMode,
    coach_hints_enabled: overrides?.coachHints ?? coachHintsEnabled,
    eval_bar_enabled: overrides?.evalBar ?? evalBarEnabled,
    opening_hints_enabled: overrides?.openingHints ?? openingHintsEnabled,
    coach_ai_only: overrides?.aiOnly ?? coachAiOnly,
    in_loop_calibration: overrides?.inLoopCal ?? inLoopCalibration,
    led_intensity: overrides?.intensity ?? ledIntensity,
    night_mode: overrides?.nMode ?? nightMode,
  });

  const persistSettings = (overrides?: {
    pos?: number;
    neg?: number;
    mode?: 'auto' | 'manual';
    col?: number;
    delay?: number;
    settle?: number;
    debounce?: number;
    window_s?: number;
    pMode?: 'auto' | 'pieces' | 'empty';
    coachHints?: boolean;
    evalBar?: boolean;
    clockBar?: boolean;
    openingHints?: boolean;
    aiOnly?: boolean;
    inLoopCal?: boolean;
    intensity?: number;
    nMode?: boolean;
  }) => {
    const merged = buildSettingsPayload(overrides);

    localStorage.setItem('scb_positive_thresh', String(merged.threshold_positive));
    localStorage.setItem('scb_negative_thresh', String(merged.threshold_negative));
    localStorage.setItem('scb_col_mode', String(merged.col_mode));
    localStorage.setItem('scb_manual_col', String(merged.manual_col));
    localStorage.setItem('scb_scan_delay', String(merged.scan_delay));
    localStorage.setItem('scb_mux_settle_ms', String(merged.mux_settle_us));
    localStorage.setItem('scb_debounce_threshold', String(merged.debounce_threshold));
    localStorage.setItem('scb_baseline_window_s', String(merged.baseline_window_s));
    localStorage.setItem('scb_pieces_mode', String(merged.pieces_mode));
    localStorage.setItem('scb_coach_hints_enabled', String(merged.coach_hints_enabled));
    localStorage.setItem('scb_eval_bar_enabled', String(merged.eval_bar_enabled));
    localStorage.setItem('scb_opening_hints_enabled', String(merged.opening_hints_enabled));
    localStorage.setItem('scb_coach_ai_only', String(merged.coach_ai_only));
    localStorage.setItem('scb_in_loop_calibration', String(merged.in_loop_calibration));
    localStorage.setItem('scb_led_intensity', String(merged.led_intensity));
    localStorage.setItem('scb_night_mode', String(merged.night_mode));

    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(async () => {
      try {
        // Built inside the callback so disabled_squares reflects the freshest WS state
        await updateBoardSettings(buildSettingsPayload(overrides));
      } catch (err) {
        console.error("Error auto-persisting settings:", err);
      }
    }, 400);
  };

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await getBoardSettings();
        setSettings(res);
        const pThresh = res.threshold_positive ?? 200;
        const nThresh = res.threshold_negative ?? 200;
        setPositiveThresh(pThresh);
        setNegativeThresh(nThresh);
        localStorage.setItem('scb_positive_thresh', String(pThresh));
        localStorage.setItem('scb_negative_thresh', String(nThresh));
        if (res.col_mode) {
          setColMode(res.col_mode);
          localStorage.setItem('scb_col_mode', res.col_mode);
        }
        if (res.manual_col !== undefined) {
          setManualCol(res.manual_col);
          localStorage.setItem('scb_manual_col', String(res.manual_col));
        }
        if (res.scan_delay !== undefined) {
          setScanDelay(res.scan_delay);
          localStorage.setItem('scb_scan_delay', String(res.scan_delay));
        }
        const settleVal = res.mux_settle_us ?? res.mux_settle_ms ?? 100;
        setMuxSettleMs(settleVal);
        localStorage.setItem('scb_mux_settle_ms', String(settleVal));
        if (res.debounce_threshold !== undefined) {
          setDebounceThreshold(res.debounce_threshold);
          localStorage.setItem('scb_debounce_threshold', String(res.debounce_threshold));
        }
        if (res.baseline_window_s !== undefined) {
          setBaselineWindowS(res.baseline_window_s);
          localStorage.setItem('scb_baseline_window_s', String(res.baseline_window_s));
        }
        if (res.pieces_mode) {
          setPiecesMode(res.pieces_mode);
          localStorage.setItem('scb_pieces_mode', res.pieces_mode);
        }
        if (res.coach_hints_enabled !== undefined) {
          setCoachHintsEnabled(res.coach_hints_enabled);
          localStorage.setItem('scb_coach_hints_enabled', String(res.coach_hints_enabled));
        }
        if (res.eval_bar_enabled !== undefined) {
          setEvalBarEnabled(res.eval_bar_enabled);
          localStorage.setItem('scb_eval_bar_enabled', String(res.eval_bar_enabled));
        }
        if (res.opening_hints_enabled !== undefined) {
          setOpeningHintsEnabled(res.opening_hints_enabled);
          localStorage.setItem('scb_opening_hints_enabled', String(res.opening_hints_enabled));
        }
        if (res.coach_ai_only !== undefined) {
          setCoachAiOnly(res.coach_ai_only);
          localStorage.setItem('scb_coach_ai_only', String(res.coach_ai_only));
        }
        if (res.in_loop_calibration !== undefined) {
          setInLoopCalibration(res.in_loop_calibration);
          localStorage.setItem('scb_in_loop_calibration', String(res.in_loop_calibration));
        }
        if (res.led_intensity !== undefined) {
          setLedIntensity(res.led_intensity);
          localStorage.setItem('scb_led_intensity', String(res.led_intensity));
        }
        if (res.night_mode !== undefined) {
          setNightMode(res.night_mode);
          localStorage.setItem('scb_night_mode', String(res.night_mode));
        }
      } catch (err) {
        console.error("Error fetching board settings:", err);
      }
    };
    if (isConnected) {
      fetchSettings();
    }
  }, [isConnected]);

  // Synchronize night mode when toggled physically on the hardware board via gesture
  const lastHwNightRef = useRef<boolean | null>(null);
  useEffect(() => {
    const hwNight = state.physical?.night_mode;
    if (hwNight === undefined || hwNight === lastHwNightRef.current) return;
    lastHwNightRef.current = hwNight;
    setNightMode(hwNight);
    localStorage.setItem('scb_night_mode', String(hwNight));
  }, [state.physical?.night_mode]);

  const handleCalibrateSquare = async (col: number, row: number) => {
    try {
      const currentReading = state.physical.adc?.[col]?.[row];
      const res = await calibrateSquare(col, row, currentReading);
      if (res.status === 'success') {
        setCalibrationStatus(`Square [${col},${row}] baseline set to ${res.baseline}`);
        setTimeout(() => setCalibrationStatus(null), 3000);
      }
    } catch (err) {
      console.error("Error calibrating square baseline:", err);
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
      const res = await updateBoardSettings(buildSettingsPayload({ disabledSquares: nextDisabled }));
      if (res.status === 'success') {
        if (res.settings) setSettings(res.settings);
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
        if (res.settings) setSettings(res.settings);
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
        if (res.settings) setSettings(res.settings);
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
    try {
      const res = await updateBoardSettings(buildSettingsPayload());
      if (res.status === 'success') {
        if (res.settings) setSettings(res.settings);
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

  const handleSaveDefaults = async () => {
    setSavingDefaults(true);
    setSaveDefaultsStatus("Saving stats as defaults...");
    try {
      const currentDisabled = state.physical.disabled_squares ?? [];
      const currentBaselines = state.physical.baselines ?? settings?.baselines;
      const res = await saveBoardDefaults({
        ...buildSettingsPayload({ disabledSquares: currentDisabled }),
        baselines: currentBaselines,
      });
      if (res.status === 'success') {
        if (res.settings) setSettings(res.settings);
        if (res.settings) {
          if (res.settings.threshold_positive !== undefined) localStorage.setItem('scb_positive_thresh', String(res.settings.threshold_positive));
          if (res.settings.threshold_negative !== undefined) localStorage.setItem('scb_negative_thresh', String(res.settings.threshold_negative));
          if (res.settings.col_mode) localStorage.setItem('scb_col_mode', res.settings.col_mode);
          if (res.settings.manual_col !== undefined) localStorage.setItem('scb_manual_col', String(res.settings.manual_col));
          if (res.settings.scan_delay !== undefined) localStorage.setItem('scb_scan_delay', String(res.settings.scan_delay));
          const settleVal = res.settings.mux_settle_us ?? res.settings.mux_settle_ms;
          if (settleVal !== undefined) localStorage.setItem('scb_mux_settle_ms', String(settleVal));
          if (res.settings.debounce_threshold !== undefined) localStorage.setItem('scb_debounce_threshold', String(res.settings.debounce_threshold));
          if (res.settings.baseline_window_s !== undefined) localStorage.setItem('scb_baseline_window_s', String(res.settings.baseline_window_s));
          if (res.settings.pieces_mode) localStorage.setItem('scb_pieces_mode', res.settings.pieces_mode);
          if (res.settings.coach_hints_enabled !== undefined) localStorage.setItem('scb_coach_hints_enabled', String(res.settings.coach_hints_enabled));
          if (res.settings.eval_bar_enabled !== undefined) localStorage.setItem('scb_eval_bar_enabled', String(res.settings.eval_bar_enabled));
          if (res.settings.opening_hints_enabled !== undefined) localStorage.setItem('scb_opening_hints_enabled', String(res.settings.opening_hints_enabled));
          if (res.settings.coach_ai_only !== undefined) localStorage.setItem('scb_coach_ai_only', String(res.settings.coach_ai_only));
          if (res.settings.in_loop_calibration !== undefined) localStorage.setItem('scb_in_loop_calibration', String(res.settings.in_loop_calibration));
          if (res.settings.led_intensity !== undefined) localStorage.setItem('scb_led_intensity', String(res.settings.led_intensity));
          if (res.settings.night_mode !== undefined) localStorage.setItem('scb_night_mode', String(res.settings.night_mode));
        }
        const nowStr = new Date().toLocaleTimeString();
        setSaveDefaultsStatus(`✓ Successfully saved to board_settings.json at ${nowStr} (${currentBaselines ? '64 Baselines' : 'Baselines'}, +${positiveThresh}/-${negativeThresh})`);
      } else {
        setSaveDefaultsStatus("Failed to save defaults");
      }
    } catch (err) {
      console.error("Error saving board defaults:", err);
      setSaveDefaultsStatus("Error saving defaults");
    } finally {
      setSavingDefaults(false);
      setTimeout(() => setSaveDefaultsStatus(null), 6000);
    }
  };

  const handleSetPiecesMode = async (newMode: 'auto' | 'pieces' | 'empty') => {
    setPiecesMode(newMode);
    persistSettings({ pMode: newMode });
    setSettingsStatus(`Board mode set to ${newMode.toUpperCase()}`);
    setTimeout(() => setSettingsStatus(null), 4000);
  };

  const isLocalGame = state.game?.is_local ?? false;
  const isMyTurn = state.status === 'PLAYING' && (isLocalGame || state.game?.turn === state.my_color);
  const isOpponentTurn = state.status === 'PLAYING' && !isLocalGame && !isMyTurn;

  // Smooth clock display: snapshot raw clocks + local receipt time whenever the server
  // heartbeat refreshes them, then drain the side-to-move client-side between updates.
  const clocksSnapshot = useMemo(() => {
    const raw = state.clocks_raw;
    if (!raw || raw.updated_at == null) return null;
    return { raw, receivedAt: Date.now() };
  }, [state.clocks_raw?.updated_at]);

  const [clockTick, setClockTick] = useState(0);
  const clockTickerActive = state.status === 'PLAYING' && clocksSnapshot !== null;
  useEffect(() => {
    if (!clockTickerActive) return;
    const t = window.setInterval(() => setClockTick((v) => v + 1), 500);
    return () => window.clearInterval(t);
  }, [clockTickerActive]);

  const displayClocks = useMemo(() => {
    void clockTick;
    const fallback = {
      white: state.clocks?.white ?? '?:??',
      black: state.clocks?.black ?? '?:??',
    };
    if (!clocksSnapshot || clocksSnapshot.raw.turn === null) return fallback;
    const { white, black, turn } = clocksSnapshot.raw;
    if (white == null || black == null) return fallback;
    const formatMs = (ms: number): string => {
      const totalSeconds = Math.floor(ms / 1000);
      const mins = Math.floor(totalSeconds / 60);
      const secs = totalSeconds % 60;
      if (mins > 0) return `${mins}:${String(secs).padStart(2, '0')}`;
      return `${secs}.${Math.floor((ms % 1000) / 100)}s`;
    };
    const elapsedMs = Date.now() - clocksSnapshot.receivedAt;
    return {
      white: turn === 'white' ? formatMs(Math.max(0, white - elapsedMs)) : formatMs(white),
      black: turn === 'black' ? formatMs(Math.max(0, black - elapsedMs)) : formatMs(black),
    };
  }, [clockTick, clocksSnapshot, state.clocks]);

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

            {/* Night Mode Ambient Backlight Switcher */}
            <button
              onClick={() => {
                const next = !nightMode;
                setNightMode(next);
                persistSettings({ nMode: next });
              }}
              title={nightMode ? "Night Mode Active (Ambient Backlight ON) - Click to Switch to Day Mode" : "Day Mode Active - Click to Switch to Night Mode"}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-bold uppercase tracking-wider font-mono transition-all duration-300 ${
                nightMode
                  ? 'bg-indigo-950/90 text-indigo-300 border-indigo-500/50 shadow-[0_0_10px_rgba(99,102,241,0.25)] hover:border-indigo-400'
                  : 'bg-amber-500/10 text-amber-300 border-amber-500/20 hover:border-amber-500/40'
              }`}
            >
              {nightMode ? <Moon size={12} className="text-indigo-400" /> : <Sun size={12} className="text-amber-400" />}
              <span>{nightMode ? 'Night Mode' : 'Day Mode'}</span>
            </button>

            {/* Cartographer's Path Opening Badge */}
            {state.opening && state.opening.name && (
              <div
                title={state.opening.variation ? `${state.opening.name} (${state.opening.variation})` : state.opening.name}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-bold font-mono transition-all duration-300 ${
                  state.opening.out_of_book
                    ? 'bg-amber-500/10 text-amber-300 border-amber-500/30 shadow-[0_0_8px_rgba(245,158,11,0.15)]'
                    : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30 shadow-[0_0_8px_rgba(16,185,129,0.15)]'
                }`}
              >
                <BookOpen size={12} className={state.opening.out_of_book ? 'text-amber-400' : 'text-emerald-400'} />
                <span className="px-1 py-0.2 rounded bg-slate-900 text-emerald-400 text-[9px] font-mono border border-emerald-500/20">
                  {state.opening.eco || 'A00'}
                </span>
                <span className="max-w-[130px] truncate">{state.opening.name}</span>
                {state.opening.out_of_book && (
                  <span className="px-1 rounded bg-amber-500/20 text-amber-400 text-[8px] uppercase tracking-wider font-bold">
                    Novelty
                  </span>
                )}
              </div>
            )}

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
              onClick={() => setActiveTab('analysis')}
              className={`px-3 py-1 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-1.5 ${
                activeTab === 'analysis' ? 'bg-violet-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Compass size={12} />
              Analysis
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
            
            {/* Capture in Progress Banner */}
            {pendingCaptureTargetCoord && (
              <div className="mb-2 bg-gradient-to-r from-rose-950/90 to-amber-950/90 border border-rose-500/50 rounded-xl px-3 py-2 text-xs text-rose-200 flex items-center justify-between shadow-lg animate-pulse">
                <div className="flex items-center gap-2">
                  <Sparkles size={14} className="text-amber-400 animate-spin" />
                  <span className="font-bold">Capture in Progress:</span>
                  <span>Opponent piece on <span className="font-mono font-bold text-amber-300 uppercase">{pendingCaptureTargetCoord}</span> lifted. Move your capturing piece to complete!</span>
                </div>
              </div>
            )}

            {/* Live Board State Mismatch Alert Banner */}
            {state.status === 'PLAYING' && !state.virtual_only && state.physical?.guardrail && !state.physical.guardrail.is_synchronized && (
              <div className="mb-2 bg-red-950/90 border border-red-500/60 rounded-xl px-3 py-2 text-xs text-red-200 flex items-center gap-2 shadow-lg">
                <AlertTriangle size={16} className="text-red-400 flex-shrink-0 animate-bounce" />
                <div className="flex flex-col text-left">
                  <span className="font-bold text-red-300">Board State Mismatch:</span>
                  <div className="text-[11px] text-red-200/90 font-mono">
                    {state.physical.guardrail.missing_pieces.length > 0 && (
                      <span>Missing piece: {state.physical.guardrail.missing_pieces.map(([c, r]) => fileRankToChessCoord(c, r)).join(', ')}. </span>
                    )}
                    {state.physical.guardrail.unexpected_pieces.length > 0 && (
                      <span>Unexpected piece: {state.physical.guardrail.unexpected_pieces.map(([c, r]) => fileRankToChessCoord(c, r)).join(', ')}.</span>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Physical Gesture Active Banner */}
            {((state.gesture && state.gesture.is_active) || (state.physical && state.physical.gesture && state.physical.gesture.is_active)) && (
              <div className="mb-2 bg-gradient-to-r from-amber-500/20 via-cyan-500/20 to-emerald-500/20 border border-cyan-400/40 rounded-xl p-3 shadow-xl backdrop-blur-md animate-pulse flex items-center justify-between gap-3 text-left">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-cyan-500/20 border border-cyan-400/30 flex items-center justify-center text-cyan-300 flex-shrink-0">
                    <Sparkles size={18} className="animate-spin text-cyan-300" style={{ animationDuration: '4s' }} />
                  </div>
                  <div className="flex flex-col">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-extrabold uppercase tracking-wider text-cyan-300">
                        Physical Board Gesture
                      </span>
                      <span className="px-1.5 py-0.2 rounded text-[9px] font-extrabold bg-cyan-500/20 border border-cyan-400/30 text-cyan-200">
                        Step {(state.gesture?.step || state.physical?.gesture?.step || 1)}/2
                      </span>
                    </div>
                    <span className="text-xs font-bold text-white">
                      {state.gesture?.hint || state.physical?.gesture?.hint || "Replay Menu Active"}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold text-slate-300 bg-slate-900/60 px-2 py-0.5 rounded border border-slate-700">
                    {((state.gesture?.time_remaining || state.physical?.gesture?.time_remaining || 0)).toFixed(1)}s
                  </span>
                </div>
              </div>
            )}

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
                {state.my_color === 'white' ? displayClocks.black : displayClocks.white}
              </div>
            </div>

            {/* 8x8 Board Container with Live Evaluation Gauge */}
            <div className="flex items-stretch w-full aspect-square bg-slate-900 overflow-hidden shadow-2xl border-x-4 border-slate-800 relative">
              {/* Vertical Eval Bar (When Eval Bar enabled and playing or AI game) */}
              {state.coach?.eval_bar_enabled && state.status === 'PLAYING' && (
                <div className="w-5 bg-slate-950 flex flex-col justify-end border-r border-slate-800 relative select-none flex-shrink-0">
                  {/* Black Bar (Top) */}
                  <div 
                    className="w-full bg-slate-800 transition-all duration-500 ease-out"
                    style={{ height: `${100 - (state.coach?.evaluation?.win_chance ?? 50)}%` }}
                  />
                  {/* White Bar (Bottom) */}
                  <div 
                    className="w-full bg-slate-200 transition-all duration-500 ease-out shadow-[0_0_8px_rgba(255,255,255,0.4)]"
                    style={{ height: `${state.coach?.evaluation?.win_chance ?? 50}%` }}
                  />
                  {/* Eval Score Badge */}
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rotate-[-90deg] text-[9px] font-mono font-extrabold tracking-tighter whitespace-nowrap px-1 py-0.5 rounded bg-slate-900/90 text-slate-200 border border-slate-700/80 shadow">
                    {state.coach?.evaluation?.mate !== null && state.coach?.evaluation?.mate !== undefined
                      ? `M${state.coach.evaluation.mate}`
                      : state.coach?.evaluation?.score_cp !== null && state.coach?.evaluation?.score_cp !== undefined
                      ? `${(state.coach.evaluation.score_cp / 100).toFixed(1)}`
                      : '0.0'}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-8 grid-rows-8 w-full h-full relative">
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
                    const isPendingCaptureTarget = pendingCaptureTargetCoord === coord;
                    const isCandidateAttacker = candidateAttackerCoords.has(coord);
                    const isGuardrailMissing = guardrailMissingCoords.has(coord);
                    const isGuardrailUnexpected = guardrailUnexpectedCoords.has(coord);

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
                        } ${
                          isPendingCaptureTarget ? 'ring-4 ring-rose-500 ring-inset bg-rose-500/30 animate-pulse shadow-[0_0_12px_rgba(244,63,94,0.8)]' : ''
                        } ${
                          isCandidateAttacker ? 'ring-2 ring-amber-400 ring-dashed ring-inset bg-amber-400/20 shadow-[0_0_8px_rgba(251,191,36,0.6)]' : ''
                        } ${
                          isGuardrailMissing ? 'ring-4 ring-amber-500 ring-dashed ring-inset bg-amber-500/25 animate-pulse shadow-[0_0_10px_rgba(245,158,11,0.7)]' : ''
                        } ${
                          isGuardrailUnexpected ? 'ring-4 ring-red-600 ring-dashed ring-inset bg-red-600/30 animate-pulse shadow-[0_0_10px_rgba(220,38,38,0.8)]' : ''
                        }`}
                      >
                        {/* Piece Icon */}
                        {renderPiece(piece)}

                        {/* Guardrail Mismatch Badge Overlay */}
                        {isGuardrailMissing && (
                          <span className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,1)]" title="Missing piece detected" />
                        )}
                        {isGuardrailUnexpected && (
                          <span className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full bg-red-500 shadow-[0_0_6px_rgba(239,68,68,1)]" title="Unexpected piece detected" />
                        )}
                        {isPendingCaptureTarget && (
                          <span className="absolute top-0.5 right-0.5 text-[9px] select-none text-rose-300 font-bold" title="Capture target">⚔</span>
                        )}

                        {/* Legal Move Indicator Dot (with Coach / Blunder Guard Color Tiers) */}
                        {isLegalDest && (
                          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                            {(() => {
                              const quality = destQualities.get(coord);
                              let ringColor = 'ring-emerald-400/80 bg-emerald-400/20';
                              let dotColor = 'bg-emerald-400/80 shadow-[0_0_8px_rgba(52,211,153,0.8)]';

                              if (quality === 'good') {
                                ringColor = 'ring-cyan-400/80 bg-cyan-400/20';
                                dotColor = 'bg-cyan-400/90 shadow-[0_0_8px_rgba(34,211,238,0.9)]';
                              } else if (quality === 'inaccuracy') {
                                ringColor = 'ring-amber-400/80 bg-amber-400/20';
                                dotColor = 'bg-amber-400/90 shadow-[0_0_8px_rgba(251,191,36,0.9)]';
                              } else if (quality === 'blunder') {
                                ringColor = 'ring-rose-500/80 bg-rose-500/30';
                                dotColor = 'bg-rose-500/90 shadow-[0_0_8px_rgba(244,63,94,0.9)]';
                              }

                              return piece !== '.' ? (
                                <div className={`w-full h-full rounded-none ring-4 ring-inset ${ringColor} animate-pulse`} />
                              ) : (
                                <div className={`w-3.5 h-3.5 rounded-full ${dotColor}`} />
                              );
                            })()}
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
                <div className={`absolute inset-0 bg-blue-950/10 border transition-all duration-300 backdrop-blur-[0.5px] z-10 pointer-events-none ${
                  state.physical?.setup?.is_setup_ready ? 'border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.15)]' : 'border-blue-500/20'
                }`}>
                  <div className={`absolute top-1 left-2 text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider text-white ${
                    state.physical?.setup?.is_setup_ready ? 'bg-emerald-600/90' : 'bg-blue-600/90'
                  }`}>
                    {state.physical?.setup?.is_setup_ready ? 'Physical Board Ready' : 'Physical Sensors Active'}
                  </div>
                  <div className="grid grid-cols-8 grid-rows-8 w-full h-full p-1 gap-1 pointer-events-auto">
                    {Array(8).fill(null).map((_, rIdx) => (
                      Array(8).fill(null).map((_, cIdx) => {
                        const isFlipped = state.my_color === 'black';
                        const fileIdx = isFlipped ? (7 - cIdx) : cIdx;
                        const rankIdx = isFlipped ? rIdx : (7 - rIdx);

                        const sensorStateVal = state.physical.grid?.[fileIdx]?.[rankIdx] ?? 0;
                        const isDisabled = (state.physical.disabled_squares ?? []).some(
                          (sq) => sq[0] === fileIdx && sq[1] === rankIdx
                        );

                        let bgClass = 'bg-slate-900/30';
                        if (isDisabled) {
                          bgClass = 'bg-slate-950/80 border border-slate-900/40 opacity-25 cursor-not-allowed';
                        } else if (sensorStateVal === 1) {
                          bgClass = 'bg-red-500/80 shadow-[0_0_8px_rgba(239,68,68,0.6)]';
                        } else if (sensorStateVal === -1) {
                          bgClass = 'bg-emerald-500/80 shadow-[0_0_8px_rgba(16,185,129,0.6)]';
                        }

                        return (
                          <div 
                            key={`sensor-${fileIdx}-${rankIdx}`}
                            title={`Square [${fileIdx},${rankIdx}] - Left-click: Calibrate baseline to current reading | Right-click: Disable`}
                            onClick={() => {
                              if (!isDisabled) handleCalibrateSquare(fileIdx, rankIdx);
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
                {state.my_color === 'black' ? displayClocks.black : displayClocks.white}
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
                    <span className="text-slate-400">Mode:</span>
                    <span className="font-mono font-bold text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      {isLocalGame ? 'Local Match (OTB)' : (state.coach?.is_ai_game ? 'Stockfish AI' : 'Lichess Online')}
                    </span>
                  </div>
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

              {/* Opponent Disconnected Alert Banner */}
              {state.status === 'PLAYING' && opponentGone && (
                <div className="bg-amber-950/40 border border-amber-500/60 rounded-xl p-3.5 flex flex-col gap-2.5 animate-pulse shadow-lg shadow-amber-950/30">
                  <div className="flex items-center gap-2.5">
                    <AlertTriangle className="text-amber-400 flex-shrink-0 animate-bounce" size={20} />
                    <div className="flex flex-col text-left">
                      <span className="text-xs font-bold text-amber-200 uppercase tracking-wider">
                        Opponent Disconnected
                      </span>
                      <span className="text-[11px] text-amber-300/90 font-mono">
                        {claimCountdown > 0
                          ? `Auto-claiming victory in ${claimCountdown}s...`
                          : 'Victory can be claimed now!'}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={handleClaimVictory}
                    disabled={isClaiming || claimCountdown > 0}
                    className="w-full bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-extrabold text-xs py-2.5 px-3 rounded-lg shadow flex items-center justify-center gap-1.5 transition-all"
                  >
                    <Trophy size={14} />
                    <span>
                      {isClaiming
                        ? 'Claiming Victory...'
                        : claimCountdown > 0
                        ? `Claim Victory (${claimCountdown}s)`
                        : 'Claim Victory Now'}
                    </span>
                  </button>
                </div>
              )}

              {/* Game Over Info */}
              {(state.status === 'GAME_OVER' || state.game?.is_game_over) && (
                <div className="bg-purple-950/40 border border-purple-500/40 rounded-xl p-3 flex flex-col items-center gap-2 text-center">
                  <CheckCircle2 className="text-purple-400" size={24} />
                  <span className="font-bold text-sm text-purple-200">Game Concluded</span>
                  <span className="text-xs text-purple-300/80 font-mono">
                    Winner: {state.game?.winner ? state.game.winner.toUpperCase() : 'Draw'} ({state.game?.end_reason || 'Finished'})
                  </span>
                  <button
                    onClick={() => {
                      setActiveTab('analysis');
                      startAnalysis();
                    }}
                    className="w-full mt-1 bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs py-2 px-3 rounded-lg shadow flex items-center justify-center gap-1.5 transition-all"
                  >
                    <Compass size={14} />
                    <span>Analyze Game ("The Grandmaster's Lens")</span>
                  </button>
                </div>
              )}
            </div>

            {/* AI Coach & Training Card */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col gap-3 text-left">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Sparkles size={14} className="text-indigo-400" />
                  AI Coach &amp; Eval Bar
                </h3>
                <span className="text-[10px] font-bold font-mono text-indigo-400 bg-indigo-950/50 px-2 py-0.5 rounded border border-indigo-500/30">
                  Stockfish 16 Multi-PV
                </span>
              </div>

              {/* Evaluation Bar & Blunder Guard Toggles */}
              <div className="flex flex-col gap-3 pt-1">
                {/* File 'h' Evaluation Bar Toggle */}
                <div className="flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="text-xs font-bold text-slate-200">Perimeter Eval Bar</span>
                    <span className="text-[10px] text-slate-400">File 'h' 8-LED White vs. Black win chance</span>
                  </div>
                  <button
                    onClick={() => {
                      const next = !evalBarEnabled;
                      setEvalBarEnabled(next);
                      persistSettings({ evalBar: next });
                    }}
                    className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors duration-300 ${
                      evalBarEnabled ? 'bg-indigo-600' : 'bg-slate-800'
                    }`}
                  >
                    <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${
                      evalBarEnabled ? 'translate-x-5' : 'translate-x-0'
                    }`} />
                  </button>
                </div>

                {/* Blunder Guard / Color-coded Moves Toggle */}
                <div className="flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="text-xs font-bold text-slate-200">Blunder Guard</span>
                    <span className="text-[10px] text-slate-400">Color-coded move destination tiers</span>
                  </div>
                  <button
                    onClick={() => {
                      const next = !coachHintsEnabled;
                      setCoachHintsEnabled(next);
                      persistSettings({ coachHints: next });
                    }}
                    className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors duration-300 ${
                      coachHintsEnabled ? 'bg-indigo-600' : 'bg-slate-800'
                    }`}
                  >
                    <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${
                      coachHintsEnabled ? 'translate-x-5' : 'translate-x-0'
                    }`} />
                  </button>
                </div>

                {/* Cartographer's Path / Opening Book Highlights Toggle */}
                <div className="flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                      <Compass size={13} className="text-emerald-400" />
                      Cartographer's Path
                    </span>
                    <span className="text-[10px] text-slate-400">Opening trailblazers (Emerald/Azure) & novelty flare</span>
                  </div>
                  <button
                    onClick={() => {
                      const next = !openingHintsEnabled;
                      setOpeningHintsEnabled(next);
                      persistSettings({ openingHints: next });
                    }}
                    className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors duration-300 ${
                      openingHintsEnabled ? 'bg-emerald-600' : 'bg-slate-800'
                    }`}
                  >
                    <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${
                      openingHintsEnabled ? 'translate-x-5' : 'translate-x-0'
                    }`} />
                  </button>
                </div>

                {/* AI Only Gate Badge / Explanation */}
                <div className="bg-indigo-950/30 border border-indigo-500/20 rounded-xl p-2.5 flex items-start gap-2 mt-1">
                  <Shield className="text-indigo-400 flex-shrink-0 mt-0.5" size={13} />
                  <p className="text-[10px] text-indigo-200/90 leading-tight">
                    <strong>AI Matches Only:</strong> Coach features and live evaluation are automatically disabled during rated online matches against human opponents to preserve fair-play on Lichess.
                  </p>
                </div>
              </div>
            </div>

            {/* In-Game Hardware Settings Card */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col gap-3 text-left">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Sliders size={14} className="text-emerald-400" />
                  Board Hardware Controls
                </h3>
                <span className={`px-2 py-0.5 rounded text-[9px] font-bold font-mono ${
                  inLoopCalibration
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                    : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                }`}>
                  {inLoopCalibration ? 'Auto Calibrating' : 'Calibration Frozen'}
                </span>
              </div>

              {/* In-Loop Auto Calibration Toggle */}
              <div className="flex items-center justify-between pt-1">
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-slate-200">In-Loop Auto Calibration</span>
                  <span className="text-[10px] text-slate-400">Dynamic baseline drift compensation</span>
                </div>
                <button
                  onClick={() => {
                    const next = !inLoopCalibration;
                    setInLoopCalibration(next);
                    persistSettings({ inLoopCal: next });
                  }}
                  className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors duration-300 ${
                    inLoopCalibration ? 'bg-emerald-600' : 'bg-slate-800'
                  }`}
                >
                  <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${
                    inLoopCalibration ? 'translate-x-5' : 'translate-x-0'
                  }`} />
                </button>
              </div>
            </div>

            {/* Analysis Mode Active Guidance Banner (When in ANALYSIS mode) */}
            {state.status === 'ANALYSIS' && (
              <div className="bg-violet-950/40 border border-violet-500/40 rounded-2xl p-4 shadow-xl flex flex-col gap-3 text-left">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="text-violet-400" size={18} />
                    <span className="text-sm font-bold text-violet-200">Analysis Mode Active</span>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-violet-900/60 text-violet-300 border border-violet-500/40">
                    Reviewing
                  </span>
                </div>
                <p className="text-xs text-violet-300/80 leading-relaxed">
                  You are currently exploring a post-game review or training drill. You can jump directly into the full Analysis Lab or start a new match below.
                </p>
                {state.analysis?.is_branching && (
                  <div className="bg-amber-950/40 border border-amber-500/40 rounded-xl px-3 py-2 flex items-center justify-between gap-2">
                    <span className="text-[11px] font-bold text-amber-200 flex items-center gap-2">
                      Off line · ply {state.analysis.anchor_ply ?? 0}
                      <span className="px-1.5 py-0.5 text-[9px] font-bold rounded-full bg-amber-500/20 text-amber-300 border border-amber-400/30">
                        {state.analysis.branch_moves?.length || 0} branch {state.analysis.branch_moves?.length === 1 ? 'move' : 'moves'}
                      </span>
                    </span>
                    <button
                      onClick={async () => {
                        await resetAnalysisBranch();
                      }}
                      className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-[11px] font-bold flex items-center gap-1.5 transition-all shadow-md shrink-0"
                    >
                      <RotateCcw size={12} />
                      Return to game
                    </button>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2 pt-1">
                  <button
                    onClick={() => setActiveTab('analysis')}
                    className="py-2 px-3 bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs rounded-xl shadow-md transition-all flex items-center justify-center gap-1.5"
                  >
                    <Sparkles size={14} /> Open Analysis Lab
                  </button>
                  <button
                    onClick={async () => {
                      await stopAnalysis();
                    }}
                    className="py-2 px-3 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs rounded-xl border border-slate-700 transition-all flex items-center justify-center gap-1.5"
                  >
                    Exit Analysis
                  </button>
                </div>
              </div>
            )}

            {/* Matchmaking Selection Controls (When IDLE, GAME_OVER, or ANALYSIS) */}
            {(state.status === 'IDLE' || state.status === 'GAME_OVER' || state.status === 'ANALYSIS') && (
              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col gap-4 text-left">
                
                {/* Lichess Board API Guidance Banner */}
                <div className="bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-3 flex items-start gap-2.5">
                  <Zap className="text-amber-400 flex-shrink-0 mt-0.5" size={16} />
                  <p className="text-[11px] text-indigo-200 leading-snug">
                    <strong className="text-white">Smart Matchmaking:</strong> Fast matches under 8 min (<span className="text-amber-300 font-mono">Bullet &amp; Blitz</span>) play instantly against <span className="text-amber-300 font-semibold">Stockfish AI</span>. For live human matchmaking on the Board API, select <span className="text-emerald-300 font-mono">Rapid (10+0 or 15+10)</span>.
                  </p>
                </div>

                {/* Board Physical Setup Status Banner */}
                {!state.virtual_only && (
                  state.physical?.setup?.is_setup_ready ? (
                    <div className="bg-emerald-950/40 border border-emerald-500/40 rounded-xl p-3 flex items-start gap-2.5 shadow-lg shadow-emerald-950/20">
                      <CheckCircle2 className="text-emerald-400 flex-shrink-0 mt-0.5" size={16} />
                      <div className="flex flex-col text-left">
                        <span className="text-xs font-bold text-emerald-200">Board Setup Complete</span>
                        <p className="text-[11px] text-emerald-300/80 leading-snug">
                          All 32 physical pieces detected in starting positions. Gesture starter pawns (<strong className="text-amber-200">a2 Night Mode</strong>, <strong className="text-violet-200">e2 Analysis</strong>, <strong className="text-emerald-200">h2 Restart</strong>) are glowing and ready!
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-amber-950/30 border border-amber-500/30 rounded-xl p-3 flex items-start gap-2.5">
                      <AlertTriangle className="text-amber-400 flex-shrink-0 mt-0.5" size={16} />
                      <div className="flex flex-col text-left">
                        <span className="text-xs font-bold text-amber-200">Setup Incomplete</span>
                        <p className="text-[11px] text-amber-300/80 leading-snug">
                          Place all White (Ranks 1–2) and Black (Ranks 7–8) pieces on their starting squares to prepare the board.
                        </p>
                      </div>
                    </div>
                  )
                )}

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

                {/* Restart Previous Game Quick-Action Button */}
                <button
                  onClick={handleRestartPrevious}
                  disabled={loading || !isConnected}
                  className="w-full mt-2 bg-gradient-to-r from-slate-900 to-indigo-950/70 hover:from-slate-850 hover:to-indigo-900/80 border border-indigo-500/40 hover:border-indigo-400 disabled:opacity-50 text-indigo-100 font-bold text-xs py-3 px-4 rounded-xl shadow-md flex items-center justify-between gap-2 transition-all active:scale-[0.98] group"
                  title="Quick restart using previous matchmaking settings (or physical gesture: lift h2, pick K=15+10 / B=10+0 / N=3+2 or toggle Rook AI/Human, replace h2)"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-300 group-hover:text-white transition-colors">
                      <RotateCcw size={15} />
                    </div>
                    <div className="flex flex-col text-left">
                      <span className="text-xs font-bold text-white">Restart Previous Game</span>
                      <span className="text-[10px] text-indigo-300/80">
                        {lastGameParams ? (
                          `${lastGameParams.time_control || '10+0'} • ${lastGameParams.opponent === 'ai' ? `Stockfish AI (Lv. ${lastGameParams.ai_level || 3})` : 'Live Human'} • ${lastGameParams.color || 'random'}`
                        ) : (
                          'Default: 10+0 Rapid • Stockfish AI'
                        )}
                      </span>
                    </div>
                  </div>
                  <span className="text-[9px] font-mono uppercase bg-indigo-900/60 border border-indigo-500/30 px-2 py-0.5 rounded text-indigo-300">
                    h2 Replay Menu
                  </span>
                </button>

                {/* Seek / Start Match Button */}
                <button
                  onClick={handleSeek}
                  disabled={loading || !isConnected}
                  className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-extrabold text-base py-3.5 rounded-xl shadow-lg shadow-blue-900/30 flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
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
      ) : activeTab === 'analysis' ? (
        /* Analysis & Training Laboratory Tab */
        <main className="flex-grow p-4 md:p-8 max-w-6xl mx-auto w-full">
          <Suspense fallback={<div className="p-6 text-slate-400">Loading analysis...</div>}>
            <AnalysisTab boardState={state} />
          </Suspense>
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
                  const isDisabled = (state.physical.disabled_squares ?? []).some(
                    (sq) => sq[0] === sensorFile && sq[1] === sensorRank
                  );

                  let cardClass = 'bg-slate-950 border-slate-850 text-slate-300';
                  let statusText = 'IDLE';
                  let statusColor = 'text-slate-600';

                  if (isDisabled) {
                    cardClass = 'bg-slate-950/20 border-slate-900/40 text-slate-600 opacity-40 line-through';
                    statusText = 'OFF';
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
                      title={`Square [${sensorFile},${sensorRank}] (${chessCoord}) - Left-click: Set baseline to current ADC (${rawAdc}) | Right-click: Disable`}
                      onClick={() => !isDisabled && handleCalibrateSquare(sensorFile, sensorRank)}
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
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10) || 200;
                      setPositiveThresh(val);
                      persistSettings({ pos: val });
                    }}
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
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10) || 200;
                      setNegativeThresh(val);
                      persistSettings({ neg: val });
                    }}
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

                {/* Save All Stats (Baselines & Thresholds) as Persistent Defaults */}
                <button
                  onClick={handleSaveDefaults}
                  disabled={savingDefaults}
                  className="w-full bg-indigo-600/25 hover:bg-indigo-600/40 text-indigo-100 border border-indigo-500/50 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-md active:scale-[0.99]"
                  title="Saves all current stats (live baselines, thresholds, timings, and mode) directly to board_settings.json"
                >
                  <BookmarkCheck size={14} className={savingDefaults ? 'animate-spin text-indigo-300' : 'text-indigo-400'} />
                  <span>{savingDefaults ? 'Writing to board_settings.json...' : 'Save Current Stats as Defaults'}</span>
                </button>
                {saveDefaultsStatus && (
                  <div className="bg-emerald-950/40 border border-emerald-500/40 rounded-xl p-2.5 flex items-center gap-2 text-left">
                    <CheckCircle2 size={14} className="text-emerald-400 flex-shrink-0" />
                    <span className="text-[11px] text-emerald-200 font-mono font-medium leading-tight">{saveDefaultsStatus}</span>
                  </div>
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

                  {/* In-Loop Calibration Switch */}
                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 mt-1">
                    <div className="flex flex-col">
                      <span className="text-[11px] font-bold text-slate-200">In-Loop Calibration</span>
                      <span className="text-[9px] text-slate-400">Continuous baseline drift compensation</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const next = !inLoopCalibration;
                        setInLoopCalibration(next);
                        persistSettings({ inLoopCal: next });
                      }}
                      className={`w-9 h-5 flex items-center rounded-full p-0.5 transition-colors duration-300 ${
                        inLoopCalibration ? 'bg-emerald-600' : 'bg-slate-800'
                      }`}
                    >
                      <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${
                        inLoopCalibration ? 'translate-x-4' : 'translate-x-0'
                      }`} />
                    </button>
                  </div>

                  {/* Night Mode Ambient Backlight Switch */}
                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 mt-1">
                    <div className="flex flex-col">
                      <span className="text-[11px] font-bold text-slate-200 flex items-center gap-1">
                        <Moon size={12} className="text-indigo-400" />
                        Night Mode (Ambient)
                      </span>
                      <span className="text-[9px] text-slate-400">Soft moonlight backlight across all 64 squares</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const next = !nightMode;
                        setNightMode(next);
                        persistSettings({ nMode: next });
                      }}
                      className={`w-9 h-5 flex items-center rounded-full p-0.5 transition-colors duration-300 ${
                        nightMode ? 'bg-indigo-600' : 'bg-slate-800'
                      }`}
                    >
                      <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${
                        nightMode ? 'translate-x-4' : 'translate-x-0'
                      }`} />
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

                {/* Master LED Intensity Slider */}
                <div className="flex flex-col gap-1.5 bg-slate-950 p-3 rounded-xl border border-slate-850 text-left">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-slate-300 font-bold flex items-center gap-1.5">
                      <Sun size={14} className="text-amber-400" />
                      Master LED Intensity
                    </span>
                    <span className="font-mono text-amber-400 font-bold bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                      {ledIntensity}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="100"
                    step="5"
                    value={ledIntensity}
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10) || 100;
                      setLedIntensity(val);
                      persistSettings({ intensity: val });
                    }}
                    className="w-full h-1.5 bg-slate-900 rounded appearance-none cursor-pointer accent-amber-500"
                  />
                  <div className="flex justify-between text-[9px] text-slate-500 font-mono">
                    <span>10% (Dim)</span>
                    <span>50%</span>
                    <span>100% (Full)</span>
                  </div>
                </div>

                {/* LED Animations & Trace Testing */}
                <div className="flex flex-col gap-2 bg-slate-950 p-3 rounded-xl border border-slate-850 text-left">
                  <div className="flex items-center gap-2 text-indigo-400">
                    <Sparkles size={14} />
                    <span className="text-xs font-bold uppercase tracking-wider">Animation & Trace Tests</span>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5 mt-1">
                    <button
                      onClick={() => handleTriggerAnimation('GAME_STARTED', { my_color: 'white' })}
                      disabled={!isConnected}
                      className="bg-amber-950/40 hover:bg-amber-900/50 border border-amber-500/30 text-amber-300 py-1.5 px-2 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1 transition-all"
                    >
                      <Zap size={11} />
                      <span>Start (White)</span>
                    </button>
                    <button
                      onClick={() => handleTriggerAnimation('GAME_STARTED', { my_color: 'black' })}
                      disabled={!isConnected}
                      className="bg-cyan-950/40 hover:bg-cyan-900/50 border border-cyan-500/30 text-cyan-300 py-1.5 px-2 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1 transition-all"
                    >
                      <Zap size={11} />
                      <span>Start (Black)</span>
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
                    <button
                      onClick={() => handleTriggerAnimation('BOARD_READY')}
                      disabled={!isConnected}
                      className="bg-emerald-950/40 hover:bg-emerald-900/50 border border-emerald-500/30 text-emerald-300 py-1.5 px-2 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1 transition-all"
                    >
                      <Sparkles size={11} />
                      <span>Board Ready (Emerald)</span>
                    </button>
                    <button
                      onClick={() => handleTriggerAnimation('SEEKING')}
                      disabled={!isConnected}
                      className="bg-cyan-950/40 hover:bg-cyan-900/50 border border-cyan-500/30 text-cyan-300 py-1.5 px-2 rounded-lg text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1 transition-all col-span-2 shadow-sm"
                    >
                      <Radar size={11} className="animate-spin" />
                      <span>Seeking / Waiting (Radar)</span>
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
                    <button
                      onClick={() => handleTestTrace('e1g1')}
                      disabled={!isConnected}
                      className="bg-blue-950/40 hover:bg-blue-900/50 text-blue-300 border border-blue-500/40 py-1.5 px-2 rounded text-[10px] font-mono font-bold flex items-center justify-center gap-1 shadow-sm"
                    >
                      <span>e1g1 ♚ ♜ (Castle O-O)</span>
                    </button>
                    <button
                      onClick={() => handleTestTrace('e1c1')}
                      disabled={!isConnected}
                      className="bg-blue-950/40 hover:bg-blue-900/50 text-blue-300 border border-blue-500/40 py-1.5 px-2 rounded text-[10px] font-mono font-bold flex items-center justify-center gap-1 shadow-sm"
                    >
                      <span>e1c1 ♚ ♜ (Castle O-O-O)</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      )}

      {/* Royal Promotion Scepter & Pawn Promotion Modal Dialog */}
      {(pendingPromotion || state.physical?.pending_promotion) && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div className="bg-slate-900 border-2 border-amber-500/60 rounded-2xl p-6 shadow-2xl max-w-md w-full flex flex-col items-center gap-4 text-center">
            <div className="flex items-center gap-2">
              <Crown className="text-amber-400" size={24} />
              <h3 className="font-extrabold text-lg text-amber-400 tracking-tight">Royal Promotion Scepter</h3>
            </div>
            
            {state.physical?.pending_promotion ? (
              <p className="text-xs text-slate-300">
                Pawn reached promotion rank! Place a piece on a physical option square or select below:
              </p>
            ) : (
              <p className="text-xs text-slate-300">Choose a piece to promote your pawn:</p>
            )}
            
            <div className="grid grid-cols-4 gap-3 w-full my-2">
              {[
                { 
                  type: 'q' as const, 
                  label: 'Queen', 
                  icon: '♕', 
                  color: 'hover:border-purple-400 hover:bg-purple-500/10 text-purple-200',
                  badge: 'text-purple-400',
                  sq: state.physical?.pending_promotion?.options?.q 
                    ? `${String.fromCharCode(97 + state.physical.pending_promotion.options.q[0])}${state.physical.pending_promotion.options.q[1] + 1}`
                    : null
                },
                { 
                  type: 'n' as const, 
                  label: 'Knight', 
                  icon: '♘', 
                  color: 'hover:border-emerald-400 hover:bg-emerald-500/10 text-emerald-200',
                  badge: 'text-emerald-400',
                  sq: state.physical?.pending_promotion?.options?.n 
                    ? `${String.fromCharCode(97 + state.physical.pending_promotion.options.n[0])}${state.physical.pending_promotion.options.n[1] + 1}`
                    : null
                },
                { 
                  type: 'r' as const, 
                  label: 'Rook', 
                  icon: '♖', 
                  color: 'hover:border-cyan-400 hover:bg-cyan-500/10 text-cyan-200',
                  badge: 'text-cyan-400',
                  sq: state.physical?.pending_promotion?.options?.r 
                    ? `${String.fromCharCode(97 + state.physical.pending_promotion.options.r[0])}${state.physical.pending_promotion.options.r[1] + 1}`
                    : null
                },
                { 
                  type: 'b' as const, 
                  label: 'Bishop', 
                  icon: '♗', 
                  color: 'hover:border-amber-400 hover:bg-amber-500/10 text-amber-200',
                  badge: 'text-amber-400',
                  sq: state.physical?.pending_promotion?.options?.b 
                    ? `${String.fromCharCode(97 + state.physical.pending_promotion.options.b[0])}${state.physical.pending_promotion.options.b[1] + 1}`
                    : null
                },
              ].map((p) => (
                <button
                  key={p.type}
                  onClick={async () => {
                    if (state.physical?.pending_promotion) {
                      try {
                        await resolvePromotion(p.type);
                      } catch (e) {
                        console.error('Error resolving physical promotion:', e);
                      }
                    } else {
                      handleExecutePromotion(p.type);
                    }
                  }}
                  className={`flex flex-col items-center justify-center p-3 rounded-xl bg-slate-950 border border-slate-800 ${p.color} transition-all hover:scale-105 shadow-md`}
                >
                  <span className="text-3xl select-none">{p.icon}</span>
                  <span className="text-[10px] font-bold mt-1 text-slate-300">{p.label}</span>
                  {p.sq && (
                    <span className={`text-[9px] font-mono font-bold mt-0.5 px-1 rounded bg-slate-900 border border-slate-700 ${p.badge}`}>
                      [{p.sq}]
                    </span>
                  )}
                </button>
              ))}
            </div>

            {state.physical?.pending_promotion ? (
              <p className="text-[10px] text-slate-400 font-mono">
                Auto-queen timer active • Lift pawn back to cancel
              </p>
            ) : (
              <button
                onClick={() => setPendingPromotion(null)}
                className="text-xs text-slate-400 hover:text-white underline mt-1"
              >
                Cancel Move
              </button>
            )}
          </div>
        </div>
      )}

      {/* The King's Bow Physical Resignation Toast */}
      {state.physical?.resignation_armed && state.status === 'PLAYING' && (
        <div className="fixed bottom-16 left-1/2 -translate-x-1/2 bg-red-950/90 border border-red-500/60 rounded-xl px-4 py-2.5 shadow-2xl z-40 flex items-center gap-3 backdrop-blur-md animate-in fade-in slide-in-from-bottom-2 duration-200">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
          <div className="flex flex-col">
            <span className="text-xs font-bold text-red-200">The King's Bow Armed</span>
            <span className="text-[10px] text-red-300/80">Replace King to surrender • Place on target to move</span>
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
