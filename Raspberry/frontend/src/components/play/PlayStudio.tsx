import React, { useMemo } from 'react';
import WebAnalysisBoard from '../board/WebAnalysisBoard';
import { digitalGridToFen } from '../board/boardUtils';
import { CapturedPiecesBar } from '../board/CapturedPiecesBar';
import { ClockWidget } from './ClockWidget';
import { MatchmakingDrawer } from './MatchmakingDrawer';
import { PhysicalGuardrailCard } from './PhysicalGuardrailCard';
import { 
  XCircle, 
  Flag, 
  Handshake, 
  AlertTriangle, 
  Trophy, 
  Sparkles, 
  CheckCircle2, 
  Compass, 
  Shield, 
  Zap
} from 'lucide-react';
import type { BoardState } from '../../hooks/useBoardState';
import type { LichessAccount, LastGameParams } from '../../api';

interface PlayStudioProps {
  state: BoardState;
  account: LichessAccount | null;
  loading: boolean;
  isConnected: boolean;
  selectedTC: string;
  setSelectedTC: (tc: string) => void;
  isRated: boolean;
  setIsRated: (r: boolean) => void;
  selectedColor: 'random' | 'white' | 'black';
  setSelectedColor: (c: 'random' | 'white' | 'black') => void;
  opponentMode: 'auto' | 'ai' | 'human';
  setOpponentMode: (m: 'auto' | 'ai' | 'human') => void;
  aiLevel: number;
  setAiLevel: (l: number) => void;
  ratingBoundary: 'any' | '100' | '200' | '300' | '500' | 'custom';
  setRatingBoundary: (b: 'any' | '100' | '200' | '300' | '500' | 'custom') => void;
  customMinRating: string;
  setCustomMinRating: (v: string) => void;
  customMaxRating: string;
  setCustomMaxRating: (v: string) => void;
  lastGameParams: LastGameParams | null;
  displayClocks: { white: string; black: string };
  destQualities: Map<string, 'best' | 'good' | 'inaccuracy' | 'blunder'>;
  onPlayMove: (uci: string) => void;
  onSeek: () => void;
  onRestartPrevious: () => void;
  onCancel: () => void;
  onResign: () => void;
  onOfferDraw: () => void;
  onClaimVictory: () => void;
  isClaiming: boolean;
  claimCountdown: number;
  onOpenAnalysis: () => void;
  coachHintsEnabled: boolean;
  onToggleCoachHints: () => void;
  evalBarEnabled: boolean;
  onToggleEvalBar: () => void;
  openingHintsEnabled: boolean;
  onToggleOpeningHints: () => void;
}

export const PlayStudio: React.FC<PlayStudioProps> = ({
  state,
  account,
  loading,
  isConnected,
  selectedTC,
  setSelectedTC,
  isRated,
  setIsRated,
  selectedColor,
  setSelectedColor,
  opponentMode,
  setOpponentMode,
  aiLevel,
  setAiLevel,
  ratingBoundary,
  setRatingBoundary,
  customMinRating,
  setCustomMinRating,
  customMaxRating,
  setCustomMaxRating,
  lastGameParams,
  displayClocks,
  destQualities,
  onPlayMove,
  onSeek,
  onRestartPrevious,
  onCancel,
  onResign,
  onOfferDraw,
  onClaimVictory,
  isClaiming,
  claimCountdown,
  onOpenAnalysis,
  coachHintsEnabled,
  onToggleCoachHints,
  evalBarEnabled,
  onToggleEvalBar,
  openingHintsEnabled,
  onToggleOpeningHints,
}) => {
  const isLocalGame = state.game?.is_local ?? false;
  const isMyTurn = state.status === 'PLAYING' && (isLocalGame || state.game?.turn === state.my_color);
  const isOpponentTurn = state.status === 'PLAYING' && !isLocalGame && !isMyTurn;

  const playFen = useMemo(() => {
    return digitalGridToFen(state.digital, state.game?.turn ?? 'white');
  }, [state.digital, state.game?.turn]);

  // Candidate attacker coordinates
  const candidateAttackerCoords = useMemo(() => {
    const coords = new Set<string>();
    const attackers = state.physical?.capture_candidate_attackers;
    if (attackers) {
      for (const [c, r] of attackers) {
        coords.add(`${String.fromCharCode(97 + c)}${r + 1}`);
      }
    }
    return coords;
  }, [state.physical]);

  const pendingCaptureTargetCoord = useMemo(() => {
    const target = state.physical?.pending_capture_target;
    if (target) {
      const [c, r] = target;
      return `${String.fromCharCode(97 + c)}${r + 1}`;
    }
    return null;
  }, [state.physical]);

  return (
    <div className="w-full flex flex-col lg:flex-row items-center lg:items-start justify-center gap-6">
      {/* Left / Center: Chessboard Stage */}
      <div className="w-full max-w-[540px] flex flex-col gap-3 shrink-0">
        {/* Capture in Progress Banner */}
        {pendingCaptureTargetCoord && (
          <div className="bg-gradient-to-r from-rose-950/90 to-amber-950/90 border border-rose-500/50 rounded-2xl px-4 py-2.5 text-xs text-rose-200 flex items-center justify-between shadow-artisan animate-pulse text-left">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-amber-400 animate-spin" />
              <span className="font-bold font-display">Capture in Progress:</span>
              <span className="font-sans">
                Piece on <strong className="font-mono text-amber-300 uppercase">{pendingCaptureTargetCoord}</strong> lifted. Complete capture!
              </span>
            </div>
          </div>
        )}

        {/* Board Setup & Guardrail Feedback */}
        <PhysicalGuardrailCard
          virtualOnly={state.virtual_only ?? false}
          isSetupReady={state.physical?.setup?.is_setup_ready}
          missingPieces={state.physical?.guardrail?.missing_pieces || []}
          unexpectedPieces={state.physical?.guardrail?.unexpected_pieces || []}
          isSynchronized={state.physical?.guardrail?.is_synchronized ?? true}
          status={state.status}
        />

        {/* Top Clock Bar: Opponent */}
        <ClockWidget
          color={state.my_color === 'black' ? 'white' : 'black'}
          playerLabel={state.game?.opponent?.username || (isLocalGame ? (state.my_color === 'black' ? 'White' : 'Black') : state.coach?.is_ai_game ? 'Stockfish AI' : 'Opponent')}
          rating={state.game?.opponent?.rating ?? undefined}
          title={state.game?.opponent?.title ?? undefined}
          timeStr={state.my_color === 'black' ? displayClocks.white : displayClocks.black}
          isTurn={isOpponentTurn}
        />

        {/* The Artisan Chessboard */}
        <WebAnalysisBoard
          fen={playFen}
          legalMoves={state.status === 'PLAYING' ? (state.game?.legal_moves ?? []) : []}
          inCheck={state.game?.is_check}
          lastMoveUci={state.game?.last_move}
          showEvalBar={evalBarEnabled && state.status === 'PLAYING'}
          winChance={state.coach?.evaluation?.win_chance}
          scoreCp={state.coach?.evaluation?.score_cp}
          mate={state.coach?.evaluation?.mate}
          onMovePlayed={onPlayMove}
          myColor={state.my_color === 'black' ? 'black' : 'white'}
          destQualities={destQualities}
          showEngineLines={false}
          showHints={false}
          adcGrid={state.physical?.adc}
          baselines={state.physical?.baselines}
          liftedSquare={state.physical?.lifted_square}
          resignationArmed={state.physical?.resignation_armed}
          kingLiftElapsed={state.physical?.king_lift_elapsed}
          activeAnimation={state.physical?.active_animation}
          ledIntensity={state.physical?.led_intensity}
          renderSquareOverlay={(_c, squareName) => {
            const isPendingCaptureTarget = pendingCaptureTargetCoord === squareName;
            const isCandidateAttacker = candidateAttackerCoords.has(squareName);

            if (!isPendingCaptureTarget && !isCandidateAttacker) return null;

            return (
              <>
                {isPendingCaptureTarget && (
                  <span
                    className="absolute top-1 right-1 text-[11px] select-none text-rose-300 font-bold z-20 pointer-events-none drop-shadow animate-bounce"
                    title="Capture target"
                  >
                    ⚔
                  </span>
                )}
                {isCandidateAttacker && (
                  <div className="absolute inset-0 ring-2 ring-amber-400 ring-dashed ring-inset bg-amber-400/20 shadow-amber-glow z-10 pointer-events-none" />
                )}
              </>
            );
          }}
          setupHighlights={{
            missingWhite: state.physical?.setup?.missing_white,
            missingBlack: state.physical?.setup?.missing_black,
            misplaced: state.physical?.setup?.misplaced_pieces,
            enabled: !state.physical?.setup?.is_setup_ready && (state.status === 'GAME_OVER' || state.status === 'IDLE' || state.status === 'SETUP'),
          }}
        />

        {/* Captured Pieces Differential Bar */}
        <CapturedPiecesBar fen={playFen} myColor={state.my_color} />

        {/* Bottom Clock Bar: Player */}
        <ClockWidget
          color={state.my_color === 'black' ? 'black' : 'white'}
          playerLabel={account?.username || (isLocalGame ? (state.my_color === 'black' ? 'Black' : 'White') : 'You')}
          rating={account?.rating || 1500}
          timeStr={state.my_color === 'black' ? displayClocks.black : displayClocks.white}
          isTurn={isMyTurn}
        />
      </div>

      {/* Right Column: Contextual Inspector Drawer */}
      <div className="w-full max-w-[500px] flex flex-col gap-4">
        {/* Seeking Mode Banner & Cancel CTA */}
        {state.status === 'SEEKING' && (
          <div className="glass-panel rounded-3xl p-5 border-blue-500/40 shadow-cyan-glow flex flex-col gap-4 animate-pulse text-left">
            <div className="flex items-center gap-3">
              <div className="p-3 rounded-2xl bg-blue-500/20 border border-blue-400/40 text-blue-300">
                <Zap size={22} className="animate-spin" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-bold font-display text-white">Seeking Opponent on Lichess</span>
                <span className="text-xs text-blue-300/80 font-mono mt-0.5">
                  {selectedTC} • {isRated ? 'Rated' : 'Casual'} • {selectedColor.toUpperCase()}
                </span>
              </div>
            </div>
            <button
              onClick={onCancel}
              disabled={loading}
              className="w-full py-3 rounded-2xl bg-rose-600 hover:bg-rose-500 text-white font-display font-bold text-xs shadow-rose-glow flex items-center justify-center gap-1.5 transition-all"
            >
              <XCircle size={15} />
              <span>Cancel Seek</span>
            </button>
          </div>
        )}

        {/* Active Game Controls & In-Game Actions */}
        {state.status === 'PLAYING' && (
          <div className="glass-panel rounded-3xl p-5 border-emerald-500/40 shadow-emerald-glow flex flex-col gap-4 text-left">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <h3 className="text-sm font-bold font-display text-white">Live Match in Progress</h3>
              </div>
              <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-mono font-bold">
                {isLocalGame ? 'Local OTB' : state.coach?.is_ai_game ? 'Stockfish' : 'Lichess'}
              </span>
            </div>

            {/* Check Notification */}
            {state.game?.is_check && (
              <div className="p-2.5 rounded-2xl bg-rose-500/25 border border-rose-500/50 text-rose-200 text-xs font-bold font-display text-center animate-pulse shadow-rose-glow">
                ⚠️ CHECK! King Under Attack!
              </div>
            )}

            {/* Opponent Disconnected Victory Claim Banner */}
            {state.game?.opponent_gone?.gone && (
              <div className="p-4 rounded-2xl bg-amber-950/60 border border-amber-500/60 flex flex-col gap-3 shadow-amber-glow">
                <div className="flex items-center gap-2.5 text-amber-200 text-xs font-bold font-display">
                  <AlertTriangle size={18} className="text-amber-400 animate-bounce" />
                  <span>Opponent Disconnected from Match</span>
                </div>
                <button
                  onClick={onClaimVictory}
                  disabled={isClaiming || claimCountdown > 0}
                  className="w-full py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-bold font-display text-xs shadow-md flex items-center justify-center gap-1.5 transition-all disabled:opacity-50"
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

            {/* In-Game Resign / Draw Actions */}
            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/80">
              <button
                onClick={onOfferDraw}
                disabled={loading}
                className="py-2.5 px-3 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-bold font-display flex items-center justify-center gap-1.5 transition-all"
              >
                <Handshake size={14} />
                <span>Offer Draw</span>
              </button>
              <button
                onClick={onResign}
                disabled={loading}
                className="py-2.5 px-3 rounded-xl bg-rose-950/40 hover:bg-rose-900/60 border border-rose-500/40 text-rose-200 text-xs font-bold font-display flex items-center justify-center gap-1.5 transition-all"
              >
                <Flag size={14} />
                <span>Resign</span>
              </button>
            </div>
          </div>
        )}

        {/* Game Over / Concluded Banner */}
        {(state.status === 'GAME_OVER' || state.game?.is_game_over) && (
          <div className="glass-panel rounded-3xl p-5 border-violet-500/40 shadow-artisan flex flex-col items-center gap-3 text-center">
            <CheckCircle2 size={28} className="text-violet-400" />
            <div className="flex flex-col">
              <span className="text-base font-bold font-display text-white">Game Concluded</span>
              <span className="text-xs text-violet-300/80 font-mono mt-0.5">
                Winner: {state.game?.winner ? state.game.winner.toUpperCase() : 'Draw'} ({state.game?.end_reason || 'Finished'})
              </span>
            </div>
            <button
              onClick={onOpenAnalysis}
              className="w-full py-3 px-4 rounded-2xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:brightness-110 text-white font-extrabold font-display text-xs shadow-md flex items-center justify-center gap-2 transition-all mt-1"
            >
              <Compass size={16} />
              <span>Analyze with Grandmaster's Lens</span>
            </button>
          </div>
        )}

        {/* Matchmaking Selection Drawer (When IDLE, GAME_OVER, or ANALYSIS) */}
        {(state.status === 'IDLE' || state.status === 'GAME_OVER' || state.status === 'ANALYSIS') && (
          <MatchmakingDrawer
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
            loading={loading}
            isConnected={isConnected}
            onSeek={onSeek}
            onRestartPrevious={onRestartPrevious}
          />
        )}

        {/* AI Coach & Eval Bar Quick Settings Card */}
        <div className="glass-panel rounded-3xl p-4 md:p-5 flex flex-col gap-3 text-left shadow-artisan">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono flex items-center gap-1.5">
              <Sparkles size={14} className="text-amber-400" />
              AI Coach &amp; Assistance
            </h3>
            <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded-full bg-slate-900 text-slate-400 border border-slate-800">
              Stockfish 16
            </span>
          </div>

          <div className="flex flex-col gap-3 pt-1">
            {/* Eval Bar Toggle */}
            <div className="flex items-center justify-between">
              <div className="flex flex-col">
                <span className="text-xs font-bold text-slate-200 font-display">Perimeter Eval Meter</span>
                <span className="text-[10px] text-slate-400 font-sans">Live Win-Chance needle on file 'h'</span>
              </div>
              <button
                onClick={onToggleEvalBar}
                className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors duration-200 ${
                  evalBarEnabled ? 'bg-amber-500' : 'bg-slate-800'
                }`}
              >
                <div
                  className={`bg-slate-950 w-4 h-4 rounded-full shadow transform transition-transform duration-200 ${
                    evalBarEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {/* Blunder Guard Toggle */}
            <div className="flex items-center justify-between">
              <div className="flex flex-col">
                <span className="text-xs font-bold text-slate-200 font-display">Blunder Guard</span>
                <span className="text-[10px] text-slate-400 font-sans">Color-coded move destination tiers</span>
              </div>
              <button
                onClick={onToggleCoachHints}
                className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors duration-200 ${
                  coachHintsEnabled ? 'bg-amber-500' : 'bg-slate-800'
                }`}
              >
                <div
                  className={`bg-slate-950 w-4 h-4 rounded-full shadow transform transition-transform duration-200 ${
                    coachHintsEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {/* Cartographer's Path Toggle */}
            <div className="flex items-center justify-between">
              <div className="flex flex-col">
                <span className="text-xs font-bold text-slate-200 font-display">Cartographer's Path</span>
                <span className="text-[10px] text-slate-400 font-sans">Opening book trailblazers &amp; novelties</span>
              </div>
              <button
                onClick={onToggleOpeningHints}
                className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors duration-200 ${
                  openingHintsEnabled ? 'bg-amber-500' : 'bg-slate-800'
                }`}
              >
                <div
                  className={`bg-slate-950 w-4 h-4 rounded-full shadow transform transition-transform duration-200 ${
                    openingHintsEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {/* Fairplay Notice */}
            <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800/80 flex items-start gap-2">
              <Shield size={13} className="text-amber-400 shrink-0 mt-0.5" />
              <span className="text-[10px] text-slate-400 font-sans leading-tight">
                Live engine coaching is automatically suppressed in rated human matches to maintain fair-play standards.
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
