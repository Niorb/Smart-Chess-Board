import React, { useState } from 'react';
import { GMGameSelector } from './GMGameSelector';
import { BlunderDrillCard } from './BlunderDrillCard';
import { EndgameDrillsCard } from './EndgameDrillsCard';
import { Crown, Flame, GraduationCap } from 'lucide-react';
import type { GMGameSummary, BoardState } from '../../hooks/useBoardState';
import type { EndgameDrillItem, BlunderAttemptResult } from '../../api';

interface AcademyStudioProps {
  boardState: BoardState;
  gmGamesList: GMGameSummary[];
  selectedGMId: string;
  onSelectGMId: (id: string) => void;
  onStartGMGame: (id: string) => void;
  endgameDrills: EndgameDrillItem[];
  onStartEndgameDrill: (id: string) => void;
  onStopEndgameDrill: () => void;
  onRequestEndgameHint: () => void;
  onResetEndgameProgress: () => void;
  onCreateCustomEndgame: (params: {
    fen: string;
    title: string;
    category: string;
    difficulty: string;
    goal: 'win' | 'draw' | 'mate';
    side_to_move: 'white' | 'black';
    description: string;
    hint?: string;
  }) => void;
  onStartBlunderDrill: (gameId?: string) => void;
  onSubmitBlunderAttempt: (uci: string) => Promise<BlunderAttemptResult | null>;
  onToggleBlunderHint: () => void;
  onApplyBlunderOpponentMove: () => void;
  loading: boolean;
}

export const AcademyStudio: React.FC<AcademyStudioProps> = ({
  boardState,
  gmGamesList,
  selectedGMId,
  onSelectGMId,
  onStartGMGame,
  endgameDrills,
  onStartEndgameDrill,
  onStopEndgameDrill,
  onRequestEndgameHint,
  onResetEndgameProgress,
  onCreateCustomEndgame,
  onStartBlunderDrill,
  onSubmitBlunderAttempt,
  onToggleBlunderHint,
  onApplyBlunderOpponentMove,
  loading,
}) => {
  const [activeTab, setActiveTab] = useState<'gm' | 'blunder' | 'endgame'>('gm');

  return (
    <div className="w-full flex flex-col gap-5 max-w-5xl mx-auto">
      {/* Academy Sub-Navigation Tabs */}
      <div className="flex items-center justify-center">
        <div className="glass-panel p-1.5 rounded-2xl flex items-center gap-1.5 shadow-md">
          <button
            onClick={() => setActiveTab('gm')}
            className={`px-4 py-2 rounded-xl text-xs font-display font-bold flex items-center gap-2 transition-all ${
              activeTab === 'gm'
                ? 'bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 shadow-amber-glow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Crown size={15} />
            <span>Grandmaster Classics</span>
          </button>

          <button
            onClick={() => setActiveTab('blunder')}
            className={`px-4 py-2 rounded-xl text-xs font-display font-bold flex items-center gap-2 transition-all ${
              activeTab === 'blunder'
                ? 'bg-gradient-to-r from-rose-500 to-rose-600 text-white shadow-rose-glow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Flame size={15} />
            <span>Blunder Drill Master</span>
          </button>

          <button
            onClick={() => setActiveTab('endgame')}
            className={`px-4 py-2 rounded-xl text-xs font-display font-bold flex items-center gap-2 transition-all ${
              activeTab === 'endgame'
                ? 'bg-gradient-to-r from-violet-500 to-violet-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <GraduationCap size={15} />
            <span>Endgame Academy</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {activeTab === 'gm' && (
        <GMGameSelector
          gmGamesList={gmGamesList}
          selectedGMId={selectedGMId}
          onSelectGMId={onSelectGMId}
          onStartGMGame={onStartGMGame}
          loading={loading}
        />
      )}

      {activeTab === 'blunder' && (
        <BlunderDrillCard
          drillState={boardState.analysis?.blunder_drill}
          onStartDrill={onStartBlunderDrill}
          onSubmitAttempt={onSubmitBlunderAttempt}
          onToggleHint={onToggleBlunderHint}
          onApplyOpponentMove={onApplyBlunderOpponentMove}
          loading={loading}
        />
      )}

      {activeTab === 'endgame' && (
        <EndgameDrillsCard
          drills={endgameDrills}
          activeDrillId={boardState.analysis?.endgame_drill?.id}
          onStartDrill={onStartEndgameDrill}
          onStopDrill={onStopEndgameDrill}
          onRequestHint={onRequestEndgameHint}
          onResetProgress={onResetEndgameProgress}
          onCreateCustomEndgame={onCreateCustomEndgame}
          loading={loading}
        />
      )}
    </div>
  );
};
