import React from 'react';
import { AlertTriangle, CheckCircle2, Shield, Sparkles } from 'lucide-react';

interface PhysicalGuardrailCardProps {
  virtualOnly: boolean;
  isSetupReady?: boolean;
  missingPieces?: Array<[number, number]>;
  unexpectedPieces?: Array<[number, number]>;
  isSynchronized?: boolean;
  status: string;
}

const fileRankToChessCoord = (c: number, r: number): string => {
  return `${String.fromCharCode(97 + c)}${r + 1}`;
};

export const PhysicalGuardrailCard: React.FC<PhysicalGuardrailCardProps> = ({
  virtualOnly,
  isSetupReady,
  missingPieces = [],
  unexpectedPieces = [],
  isSynchronized = true,
  status,
}) => {
  if (virtualOnly) {
    return (
      <div className="p-3 rounded-2xl bg-purple-950/30 border border-purple-500/30 flex items-center gap-2.5 text-left">
        <Shield size={16} className="text-purple-400 shrink-0" />
        <div className="flex flex-col">
          <span className="text-xs font-bold text-purple-200 font-display">Virtual-Only Match Mode</span>
          <span className="text-[10px] text-purple-300/80 font-sans">
            Moves are played exclusively on the web canvas. Hardware sensors are bypassed.
          </span>
        </div>
      </div>
    );
  }

  // Active game mismatch alert
  if (status === 'PLAYING' && !isSynchronized) {
    return (
      <div className="p-3.5 rounded-2xl bg-rose-950/60 border border-rose-500/60 shadow-rose-glow flex items-start gap-3 text-left animate-pulse">
        <AlertTriangle size={18} className="text-rose-400 shrink-0 mt-0.5 animate-bounce" />
        <div className="flex flex-col">
          <span className="text-xs font-bold text-rose-200 font-display">Physical Board Desynchronized</span>
          <div className="text-[11px] text-rose-300 font-mono mt-0.5 space-y-0.5">
            {missingPieces.length > 0 && (
              <div>Missing piece: {missingPieces.map(([c, r]) => fileRankToChessCoord(c, r)).join(', ')}</div>
            )}
            {unexpectedPieces.length > 0 && (
              <div>Unexpected piece: {unexpectedPieces.map(([c, r]) => fileRankToChessCoord(c, r)).join(', ')}</div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Setup mode feedback
  if (status === 'IDLE' || status === 'GAME_OVER' || status === 'SETUP') {
    if (isSetupReady) {
      return (
        <div className="p-3.5 rounded-2xl bg-emerald-950/40 border border-emerald-500/40 shadow-emerald-glow flex items-start gap-3 text-left">
          <CheckCircle2 size={18} className="text-emerald-400 shrink-0 mt-0.5" />
          <div className="flex flex-col">
            <span className="text-xs font-bold text-emerald-200 font-display">Board Setup Complete</span>
            <p className="text-[11px] text-emerald-300/90 font-sans leading-snug mt-0.5">
              All 32 physical pieces detected in starting positions. Ready for match seek!
            </p>
          </div>
        </div>
      );
    } else {
      return (
        <div className="p-3.5 rounded-2xl bg-amber-950/40 border border-amber-500/40 flex items-start gap-3 text-left">
          <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />
          <div className="flex flex-col">
            <span className="text-xs font-bold text-amber-200 font-display">Setup Starting Pieces</span>
            <p className="text-[11px] text-amber-300/80 font-sans leading-snug mt-0.5">
              Place White pieces on Ranks 1–2 and Black pieces on Ranks 7–8 to prepare the board.
            </p>
          </div>
        </div>
      );
    }
  }

  return null;
};
