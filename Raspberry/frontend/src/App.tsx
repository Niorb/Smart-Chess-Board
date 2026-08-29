import { useState, useEffect, useMemo, useRef, lazy, Suspense } from 'react';
import { useBoardState } from './hooks/useBoardState';
import { ThemeProvider } from './context/ThemeContext';
import { useArtisanTheme } from './context/useArtisanTheme';
import { StudioSidebar } from './components/layout/StudioSidebar';
import { StudioHeader } from './components/layout/StudioHeader';
import { ToastNotification, type ToastMessage } from './components/layout/ToastNotification';
import { PlayStudio } from './components/play/PlayStudio';
import { AcademyStudio } from './components/academy/AcademyStudio';
import { HardwareWorkshop } from './components/hardware/HardwareWorkshop';
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
  getGMGames,
  startGMGame,
  getEndgameDrills,
  startEndgameDrill,
  stopEndgameDrill,
  requestEndgameHint,
  resetEndgameProgress,
  createCustomEndgame,
  startBlunderDrill,
  submitBlunderAttempt,
  toggleBlunderHint,
  applyBlunderOpponentMove,
  type LichessAccount, 
  type LastGameParams, 
  type BoardSettings,
  type EndgameDrillItem,
  type BlunderAttemptResult
} from './api';
import type { GMGameSummary } from './hooks/useBoardState';

const AnalysisTab = lazy(() => import('./components/analysis/AnalysisTab'));

function StudioApp() {
  const { state, isConnected } = useBoardState();
  const { activeView, setActiveView } = useArtisanTheme();

  const [loading, setLoading] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = (type: 'success' | 'error' | 'info' | 'warning', message: string, title?: string) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, type, message, title }]);
  };

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Lichess Account & Matchmaking
  const [account, setAccount] = useState<LichessAccount | null>(null);
  const [selectedTC, setSelectedTC] = useState<string>('10+0');
  const [isRated, setIsRated] = useState<boolean>(true);
  const [selectedColor, setSelectedColor] = useState<'random' | 'white' | 'black'>('random');
  const [opponentMode, setOpponentMode] = useState<'auto' | 'ai' | 'human'>('auto');
  const [aiLevel, setAiLevel] = useState<number>(3);
  const [ratingBoundary, setRatingBoundary] = useState<'any' | '100' | '200' | '300' | '500' | 'custom'>('any');
  const [customMinRating, setCustomMinRating] = useState<string>('1200');
  const [customMaxRating, setCustomMaxRating] = useState<string>('1800');
  const [lastGameParams, setLastGameParams] = useState<LastGameParams | null>(null);

  // Academy States
  const [gmGamesList, setGmGamesList] = useState<GMGameSummary[]>([]);
  const [selectedGMId, setSelectedGMId] = useState<string>('kasparov_topalov_1999');
  const [endgameDrills, setEndgameDrills] = useState<EndgameDrillItem[]>([]);

  // Disconnection & Victory Claiming State
  const [isClaiming, setIsClaiming] = useState<boolean>(false);
  const opponentGone = state.game?.opponent_gone?.gone ?? false;
  const claimWinIn = state.game?.opponent_gone?.claim_win_in ?? 0;
  const claimCountdown = opponentGone ? Math.max(0, Math.ceil(claimWinIn)) : 0;

  // Board Hardware Settings State
  const [, setSettings] = useState<BoardSettings | null>(null);
  const [positiveThresh, setPositiveThresh] = useState<number>(() => {
    const saved = localStorage.getItem('scb_positive_thresh');
    return saved ? parseInt(saved, 10) || 200 : 200;
  });
  const [negativeThresh, setNegativeThresh] = useState<number>(() => {
    const saved = localStorage.getItem('scb_negative_thresh');
    return saved ? parseInt(saved, 10) || 200 : 200;
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
  const [savingDefaults, setSavingDefaults] = useState(false);
  const [saveDefaultsStatus, setSaveDefaultsStatus] = useState<string | null>(null);

  const effectiveNightMode = state.physical?.night_mode !== undefined ? state.physical.night_mode : nightMode;

  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // Fetch initial account, params, GM games, and endgame drills
  useEffect(() => {
    if (!isConnected) return;
    let cancelled = false;

    getLichessAccount().then((acc) => {
      if (!cancelled && acc) setAccount(acc);
    }).catch(() => {});

    getLastGameParams().then((res) => {
      if (!cancelled && res.status === 'success' && res.last_game_params) {
        setLastGameParams(res.last_game_params);
      }
    }).catch(() => {});

    getGMGames().then((data) => {
      if (!cancelled && Array.isArray(data)) setGmGamesList(data);
    }).catch(() => {});

    getEndgameDrills().then((data) => {
      if (!cancelled && Array.isArray(data)) setEndgameDrills(data);
    }).catch(() => {});

    getBoardSettings().then((res) => {
      if (!cancelled && res) {
        setSettings(res);
        if (res.threshold_positive !== undefined) setPositiveThresh(res.threshold_positive);
        if (res.threshold_negative !== undefined) setNegativeThresh(res.threshold_negative);
        if (res.scan_delay !== undefined) setScanDelay(res.scan_delay);
        const settle = res.mux_settle_us ?? res.mux_settle_ms;
        if (settle !== undefined) setMuxSettleMs(settle);
        if (res.debounce_threshold !== undefined) setDebounceThreshold(res.debounce_threshold);
        if (res.baseline_window_s !== undefined) setBaselineWindowS(res.baseline_window_s);
        if (res.pieces_mode) setPiecesMode(res.pieces_mode);
        if (res.coach_hints_enabled !== undefined) setCoachHintsEnabled(res.coach_hints_enabled);
        if (res.eval_bar_enabled !== undefined) setEvalBarEnabled(res.eval_bar_enabled);
        if (res.opening_hints_enabled !== undefined) setOpeningHintsEnabled(res.opening_hints_enabled);
        if (res.in_loop_calibration !== undefined) setInLoopCalibration(res.in_loop_calibration);
        if (res.led_intensity !== undefined) setLedIntensity(res.led_intensity);
        if (res.night_mode !== undefined) setNightMode(res.night_mode);
      }
    }).catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [isConnected]);

  // Move Quality hints map
  const destQualities = useMemo(() => {
    const map = new Map<string, 'best' | 'good' | 'inaccuracy' | 'blunder'>();
    if (!state.coach?.enabled || !state.coach?.lifted_move_hints) return map;
    for (const hint of state.coach.lifted_move_hints) {
      map.set(hint.uci.slice(2, 4), hint.tier);
    }
    return map;
  }, [state.coach]);

  // Clocks smooth interpolation ticker
  const [now, setNow] = useState<number>(0);
  const clockTickerActive = state.status === 'PLAYING' && !!state.clocks_raw && state.clocks_raw.updated_at != null;
  useEffect(() => {
    if (!clockTickerActive) return;
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [clockTickerActive]);

  const displayClocks = useMemo(() => {
    const fallback = {
      white: state.clocks?.white ?? '?:??',
      black: state.clocks?.black ?? '?:??',
    };
    const raw = state.clocks_raw;
    if (!raw || raw.turn === null || raw.updated_at == null || raw.white == null || raw.black == null) {
      return fallback;
    }
    const formatMs = (ms: number): string => {
      const totalSeconds = Math.floor(ms / 1000);
      const mins = Math.floor(totalSeconds / 60);
      const secs = totalSeconds % 60;
      if (mins > 0) return `${mins}:${String(secs).padStart(2, '0')}`;
      return `${secs}.${Math.floor((ms % 1000) / 100)}s`;
    };
    const updatedMs = raw.updated_at > 1e11 ? raw.updated_at : raw.updated_at * 1000;
    const elapsedMs = now > updatedMs ? now - updatedMs : 0;
    return {
      white: raw.turn === 'white' ? formatMs(Math.max(0, raw.white - elapsedMs)) : formatMs(raw.white),
      black: raw.turn === 'black' ? formatMs(Math.max(0, raw.black - elapsedMs)) : formatMs(raw.black),
    };
  }, [now, state.clocks_raw, state.clocks]);

  const buildSettingsPayload = (overrides?: Record<string, unknown>) => ({
    threshold_positive: (overrides?.pos as number) ?? positiveThresh,
    threshold_negative: (overrides?.neg as number) ?? negativeThresh,
    scan_delay: (overrides?.delay as number) ?? scanDelay,
    mux_settle_us: (overrides?.settle as number) ?? muxSettleMs,
    debounce_threshold: (overrides?.debounce as number) ?? debounceThreshold,
    baseline_window_s: (overrides?.window_s as number) ?? baselineWindowS,
    disabled_squares: (overrides?.disabledSquares as number[][]) ?? stateRef.current.physical.disabled_squares ?? [],
    pieces_mode: (overrides?.pMode as 'auto' | 'pieces' | 'empty') ?? piecesMode,
    coach_hints_enabled: (overrides?.coachHints as boolean) ?? coachHintsEnabled,
    eval_bar_enabled: (overrides?.evalBar as boolean) ?? evalBarEnabled,
    opening_hints_enabled: (overrides?.openingHints as boolean) ?? openingHintsEnabled,
    in_loop_calibration: (overrides?.inLoopCal as boolean) ?? inLoopCalibration,
    led_intensity: (overrides?.intensity as number) ?? ledIntensity,
    night_mode: (overrides?.nMode as boolean) ?? effectiveNightMode,
  });

  const persistSettings = (overrides?: Record<string, unknown>) => {
    const payload = buildSettingsPayload(overrides);
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(async () => {
      try {
        await updateBoardSettings(payload);
      } catch (err) {
        console.error('Error auto-persisting settings:', err);
      }
    }, 400);
  };

  // Matchmaking Handlers
  const handleSeek = async () => {
    setLoading(true);
    try {
      await seekGame({
        timeControl: selectedTC,
        rated: isRated,
        color: selectedColor,
        opponent: opponentMode,
        aiLevel: aiLevel,
      });
      addToast('info', `Seeking match (${selectedTC}) on Lichess...`, 'Matchmaking');
    } catch (err) {
      console.error('Error seeking match:', err);
      addToast('error', 'Failed to initiate match seek', 'Error');
    } finally {
      setLoading(false);
    }
  };

  const handleRestartPrevious = async () => {
    setLoading(true);
    try {
      await restartPreviousGame();
      addToast('success', 'Restarted previous match settings', 'Rematch');
    } catch (err) {
      console.error('Error restarting previous game:', err);
      addToast('error', 'Could not restart previous game', 'Error');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    setLoading(true);
    try {
      await cancelGame();
      addToast('info', 'Seek request cancelled', 'Cancelled');
    } catch (err) {
      console.error('Error cancelling match:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleResign = async () => {
    if (!window.confirm('Are you sure you want to resign the game?')) return;
    setLoading(true);
    try {
      await resignGame();
      addToast('warning', 'Resigned the game', 'Game Over');
    } catch (err) {
      console.error('Error resigning game:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleOfferDraw = async () => {
    setLoading(true);
    try {
      await offerDraw(true);
      addToast('info', 'Draw offered to opponent', 'Draw Offer');
    } catch (err) {
      console.error('Error offering draw:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleClaimVictory = async () => {
    setIsClaiming(true);
    try {
      await claimVictory();
      addToast('success', 'Victory claimed by disconnection!', 'Trophy');
    } catch (err) {
      console.error('Error claiming victory:', err);
    } finally {
      setIsClaiming(false);
    }
  };

  const handlePlayMove = async (uci: string) => {
    if (state.status !== 'PLAYING' || uci.length < 4) return;
    const fromSquare = uci.slice(0, 2);
    const toSquare = uci.slice(2, 4);
    const promotionPiece = uci.length > 4 ? uci.slice(4) : undefined;
    try {
      const res = await makeMove(fromSquare, toSquare, promotionPiece);
      if (res.status !== 'success') {
        console.warn('Move rejected:', res.message);
      }
    } catch (err) {
      console.error('Error making move:', err);
    }
  };

  const handleToggleVirtualOnly = async () => {
    const nextMode = !state.virtual_only;
    try {
      await setGameMode(nextMode);
      addToast('info', nextMode ? 'Switched to Virtual Only' : 'Switched to Physical Hardware Board', 'Mode');
    } catch (err) {
      console.error('Error updating game mode:', err);
    }
  };

  // Academy Handlers
  const handleStartGMGame = async (id: string) => {
    setLoading(true);
    try {
      await startGMGame(id);
      setActiveView('analysis');
      addToast('success', `Loaded Grandmaster game on physical board!`, 'Academy');
    } catch (err) {
      console.error('Error starting GM game:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleStartEndgameDrill = async (id: string) => {
    setLoading(true);
    try {
      await startEndgameDrill({ drill_id: id });
      setActiveView('analysis');
      addToast('success', `Loaded Endgame Drill!`, 'Endgame Academy');
    } catch (err) {
      console.error('Error starting endgame drill:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleStopEndgameDrill = async () => {
    try {
      await stopEndgameDrill();
      addToast('info', 'Exited Endgame Drill', 'Endgame');
    } catch (err) {
      console.error('Error stopping endgame drill:', err);
    }
  };

  const handleRequestEndgameHint = async () => {
    try {
      await requestEndgameHint();
    } catch (err) {
      console.error('Error requesting endgame hint:', err);
    }
  };

  const handleResetEndgameProgress = async () => {
    try {
      await resetEndgameProgress();
      addToast('info', 'Reset endgame progress', 'Endgame');
    } catch (err) {
      console.error('Error resetting endgame progress:', err);
    }
  };

  const handleCreateCustomEndgame = async (params: {
    fen: string;
    title: string;
    category: string;
    difficulty: number;
    goal: 'win' | 'draw' | 'mate';
    side_to_move: 'white' | 'black';
    description: string;
    hint?: string;
  }) => {
    try {
      const created = await createCustomEndgame({
        fen: params.fen,
        title: params.title,
        player_color: params.side_to_move,
        target_goal: params.goal,
        difficulty: params.difficulty,
        description: params.description,
        hint: params.hint,
      });
      const data = await getEndgameDrills();
      if (Array.isArray(data)) setEndgameDrills(data);
      if (created && (created as unknown as { drill_id?: string }).drill_id) {
        await startEndgameDrill({ drill_id: (created as unknown as { drill_id?: string }).drill_id });
        setActiveView('analysis');
      }
      addToast('success', `Created custom endgame "${params.title}"!`, 'Saved');
    } catch (err) {
      console.error('Error creating custom endgame:', err);
    }
  };

  const handleStartBlunderDrill = async (index?: number) => {
    setLoading(true);
    try {
      await startBlunderDrill(index ?? 0);
      addToast('success', 'Generated new tactical blunder drill!', 'Drill');
    } catch (err) {
      console.error('Error starting blunder drill:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitBlunderAttempt = async (uci: string): Promise<BlunderAttemptResult | null> => {
    try {
      return await submitBlunderAttempt(uci);
    } catch (err) {
      console.error('Error submitting blunder attempt:', err);
      return null;
    }
  };

  const handleToggleBlunderHint = async () => {
    try {
      await toggleBlunderHint();
    } catch (err) {
      console.error('Error toggling blunder hint:', err);
    }
  };

  const handleApplyBlunderOpponentMove = async () => {
    try {
      await applyBlunderOpponentMove();
    } catch (err) {
      console.error('Error applying opponent move:', err);
    }
  };

  // Hardware Handlers
  const handleCalibrateSquare = async (col: number, row: number) => {
    try {
      const currentReading = state.physical.adc?.[col]?.[row];
      const res = await calibrateSquare(col, row, currentReading);
      if (res.status === 'success') {
        addToast('success', `Square baseline set to ${res.baseline}`, 'Calibrated');
      }
    } catch (err) {
      console.error('Error calibrating square:', err);
    }
  };

  const handleToggleDisableSquare = async (col: number, row: number) => {
    const currentDisabled = state.physical.disabled_squares ?? [];
    const exists = currentDisabled.some((sq) => sq[0] === col && sq[1] === row);
    const nextDisabled = exists
      ? currentDisabled.filter((sq) => !(sq[0] === col && sq[1] === row))
      : [...currentDisabled, [col, row]];

    try {
      const res = await updateBoardSettings(buildSettingsPayload({ disabledSquares: nextDisabled }));
      if (res.status === 'success' && res.settings) setSettings(res.settings);
    } catch (err) {
      console.error('Error updating disabled squares:', err);
    }
  };

  const handleCalibrate = async () => {
    setCalibrating(true);
    setCalibrationStatus('Calibrating... Keep board clear');
    try {
      const res = await calibrateBoard();
      if (res.status === 'success') {
        if (res.settings) setSettings(res.settings);
        setCalibrationStatus('Success: Baselines mapped!');
        addToast('success', 'Board calibrated successfully!', 'Calibration');
      } else {
        setCalibrationStatus(`Failed: ${res.message}`);
      }
    } catch (err) {
      console.error(err);
      setCalibrationStatus('Error: Calibration failed');
    } finally {
      setCalibrating(false);
      setTimeout(() => setCalibrationStatus(null), 4000);
    }
  };

  const handleCalibrateWithPieces = async () => {
    setCalibrating(true);
    setCalibrationStatus('Calibrating with pieces in place...');
    try {
      const res = await calibrateBoardWithPieces();
      if (res.status === 'success') {
        if (res.settings) setSettings(res.settings);
        setCalibrationStatus('Success: Baselines mapped from middle ranks!');
        addToast('success', 'Mapped baselines from vacant ranks!', 'Calibration');
      } else {
        setCalibrationStatus(`Failed: ${res.message}`);
      }
    } catch (err) {
      console.error(err);
      setCalibrationStatus('Error: Calibration failed');
    } finally {
      setCalibrating(false);
      setTimeout(() => setCalibrationStatus(null), 4000);
    }
  };

  const handleSaveDefaults = async () => {
    setSavingDefaults(true);
    setSaveDefaultsStatus('Saving to board_settings.json...');
    try {
      const currentDisabled = state.physical.disabled_squares ?? [];
      const currentBaselines = state.physical.baselines;
      const res = await saveBoardDefaults({
        ...buildSettingsPayload({ disabledSquares: currentDisabled }),
        baselines: currentBaselines,
      });
      if (res.status === 'success') {
        if (res.settings) setSettings(res.settings);
        const time = new Date().toLocaleTimeString();
        setSaveDefaultsStatus(`✓ Saved to board_settings.json at ${time}`);
        addToast('success', 'Permanent hardware defaults saved!', 'Saved');
      }
    } catch (err) {
      console.error('Error saving board defaults:', err);
      setSaveDefaultsStatus('Error saving defaults');
    } finally {
      setSavingDefaults(false);
      setTimeout(() => setSaveDefaultsStatus(null), 6000);
    }
  };

  const handleTestLeds = async () => {
    try {
      await testLeds();
      addToast('info', 'RGB LED light test pattern triggered', 'LEDs');
    } catch (err) {
      console.error(err);
    }
  };

  const handleClearLeds = async () => {
    try {
      await clearAllLeds();
      addToast('info', 'All LEDs cleared', 'LEDs');
    } catch (err) {
      console.error(err);
    }
  };

  const handleTriggerAnimation = async (name: string, params?: Record<string, unknown>) => {
    try {
      await triggerAnimation(name, params);
    } catch (err) {
      console.error(err);
    }
  };

  const handleTestTrace = async (uci: string, isCapture = false) => {
    try {
      await testMoveTrace({ uci, is_capture: isCapture });
    } catch (err) {
      console.error(err);
    }
  };

  const handleStopAnalysis = async () => {
    setLoading(true);
    try {
      await stopAnalysis();
      setActiveView('play');
      addToast('info', 'Exited analysis mode. Board returned to ready state.', 'Analysis Concluded');
    } catch (err) {
      console.error('Error stopping analysis mode:', err);
      addToast('error', 'Failed to stop analysis mode', 'Error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex bg-[#0b0f17] text-slate-100 p-3 md:p-6 select-none font-sans overflow-x-hidden">
      <div className="w-full max-w-[1440px] mx-auto flex gap-6">
        {/* Studio Sidebar (Desktop) */}
        <StudioSidebar
          status={state.status}
          isConnected={isConnected}
          virtualOnly={state.virtual_only ?? false}
          onToggleVirtualOnly={handleToggleVirtualOnly}
          nightMode={effectiveNightMode}
          onToggleNightMode={() => {
            const next = !nightMode;
            setNightMode(next);
            persistSettings({ nMode: next });
          }}
          hasActiveGesture={state.gesture?.is_active || state.physical?.gesture?.is_active}
          onStopAnalysis={handleStopAnalysis}
        />

        {/* Main Studio View Area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Top Header */}
          <StudioHeader
            account={account}
            status={state.status}
            isConnected={isConnected}
            virtualOnly={state.virtual_only ?? false}
            onToggleVirtualOnly={handleToggleVirtualOnly}
            nightMode={effectiveNightMode}
            onToggleNightMode={() => {
              const next = !nightMode;
              setNightMode(next);
              persistSettings({ nMode: next });
            }}
            opening={state.opening ? {
              name: state.opening.name,
              variation: state.opening.variation ?? undefined,
              eco: state.opening.eco,
              out_of_book: state.opening.out_of_book,
            } : null}
            onStopAnalysis={handleStopAnalysis}
          />

          {/* Dynamic Active Workspace View */}
          <main className="flex-1 flex flex-col justify-start">
            {activeView === 'play' && (
              <PlayStudio
                state={state}
                account={account}
                loading={loading}
                isConnected={isConnected}
                selectedTC={selectedTC}
                setSelectedTC={setSelectedTC}
                isRated={isRated}
                setIsRated={setIsRated}
                selectedColor={selectedColor}
                setSelectedColor={setSelectedColor}
                opponentMode={opponentMode}
                setOpponentMode={setOpponentMode}
                aiLevel={aiLevel}
                setAiLevel={setAiLevel}
                ratingBoundary={ratingBoundary}
                setRatingBoundary={setRatingBoundary}
                customMinRating={customMinRating}
                setCustomMinRating={setCustomMinRating}
                customMaxRating={customMaxRating}
                setCustomMaxRating={setCustomMaxRating}
                lastGameParams={lastGameParams}
                displayClocks={displayClocks}
                destQualities={destQualities}
                onPlayMove={handlePlayMove}
                onSeek={handleSeek}
                onRestartPrevious={handleRestartPrevious}
                onCancel={handleCancel}
                onResign={handleResign}
                onOfferDraw={handleOfferDraw}
                onClaimVictory={handleClaimVictory}
                isClaiming={isClaiming}
                claimCountdown={claimCountdown}
                onOpenAnalysis={() => {
                  setActiveView('analysis');
                  startAnalysis();
                }}
                coachHintsEnabled={coachHintsEnabled}
                onToggleCoachHints={() => {
                  const next = !coachHintsEnabled;
                  setCoachHintsEnabled(next);
                  persistSettings({ coachHints: next });
                }}
                evalBarEnabled={evalBarEnabled}
                onToggleEvalBar={() => {
                  const next = !evalBarEnabled;
                  setEvalBarEnabled(next);
                  persistSettings({ evalBar: next });
                }}
                openingHintsEnabled={openingHintsEnabled}
                onToggleOpeningHints={() => {
                  const next = !openingHintsEnabled;
                  setOpeningHintsEnabled(next);
                  persistSettings({ openingHints: next });
                }}
              />
            )}

            {activeView === 'analysis' && (
              <Suspense fallback={<div className="p-12 text-slate-400 font-mono">Loading Grandmaster Analysis...</div>}>
                <AnalysisTab boardState={state} />
              </Suspense>
            )}

            {activeView === 'academy' && (
              <AcademyStudio
                boardState={state}
                gmGamesList={gmGamesList}
                selectedGMId={selectedGMId}
                onSelectGMId={setSelectedGMId}
                onStartGMGame={handleStartGMGame}
                endgameDrills={endgameDrills}
                onStartEndgameDrill={handleStartEndgameDrill}
                onStopEndgameDrill={handleStopEndgameDrill}
                onRequestEndgameHint={handleRequestEndgameHint}
                onResetEndgameProgress={handleResetEndgameProgress}
                onCreateCustomEndgame={handleCreateCustomEndgame}
                onStartBlunderDrill={handleStartBlunderDrill}
                onSubmitBlunderAttempt={handleSubmitBlunderAttempt}
                onToggleBlunderHint={handleToggleBlunderHint}
                onApplyBlunderOpponentMove={handleApplyBlunderOpponentMove}
                loading={loading}
              />
            )}

            {activeView === 'hardware' && (
              <HardwareWorkshop
                state={state}
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
                nightMode={effectiveNightMode}
                setNightMode={setNightMode}
                piecesMode={piecesMode}
                onSetPiecesMode={(m) => {
                  setPiecesMode(m);
                  persistSettings({ pMode: m });
                }}
                onCalibrate={handleCalibrate}
                onCalibrateWithPieces={handleCalibrateWithPieces}
                onSaveDefaults={handleSaveDefaults}
                calibrating={calibrating}
                savingDefaults={savingDefaults}
                calibrationStatus={calibrationStatus}
                saveDefaultsStatus={saveDefaultsStatus}
                persistSettings={persistSettings}
                onCalibrateSquare={handleCalibrateSquare}
                onToggleDisableSquare={handleToggleDisableSquare}
                onTestLeds={handleTestLeds}
                onClearLeds={handleClearLeds}
                onTriggerAnimation={handleTriggerAnimation}
                onTestTrace={handleTestTrace}
              />
            )}
          </main>
        </div>
      </div>

      {/* Toast Notification Container */}
      <ToastNotification toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <StudioApp />
    </ThemeProvider>
  );
}
