import React, { useState } from 'react';
import { 
  GraduationCap, 
  CheckCircle2, 
  PlayCircle, 
  Lightbulb, 
  Plus, 
  RotateCcw, 
  Star,
  Target,
  Sparkles,
  X
} from 'lucide-react';
import type { EndgameDrillItem } from '../../api';

interface EndgameDrillsCardProps {
  drills: EndgameDrillItem[];
  activeDrillId?: string | null;
  onStartDrill: (drillId: string) => void;
  onStopDrill: () => void;
  onRequestHint: () => void;
  onResetProgress: () => void;
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
  loading: boolean;
}

export const EndgameDrillsCard: React.FC<EndgameDrillsCardProps> = ({
  drills,
  activeDrillId,
  onStartDrill,
  onStopDrill,
  onRequestHint,
  onResetProgress,
  onCreateCustomEndgame,
  loading,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Form states for custom endgame
  const [fenInput, setFenInput] = useState('');
  const [titleInput, setTitleInput] = useState('');
  const [goalInput, setGoalInput] = useState<'win' | 'draw' | 'mate'>('win');
  const [colorInput, setColorInput] = useState<'white' | 'black'>('white');
  const [descInput, setDescInput] = useState('');
  const [hintInput, setHintInput] = useState('');

  const filteredDrills = drills.filter((d) => {
    if (selectedCategory === 'all') return true;
    return d.category.toLowerCase() === selectedCategory.toLowerCase();
  });

  const handleCreateCustom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!fenInput.trim() || !titleInput.trim()) return;
    onCreateCustomEndgame({
      fen: fenInput.trim(),
      title: titleInput.trim(),
      category: 'custom',
      difficulty: 'Intermediate',
      goal: goalInput,
      side_to_move: colorInput,
      description: descInput.trim() || 'Custom theoretical endgame position',
      hint: hintInput.trim() || undefined,
    });
    setIsModalOpen(false);
    setFenInput('');
    setTitleInput('');
  };

  return (
    <div className="glass-panel rounded-3xl p-5 flex flex-col gap-4 text-left shadow-artisan">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-violet-500/20 text-violet-300 border border-violet-500/40">
            <GraduationCap size={18} />
          </div>
          <div>
            <h3 className="text-sm font-bold font-display text-white">Endgame Academy &amp; Syzygy</h3>
            <p className="text-[11px] text-slate-400 font-sans">Master theoretical endgames and 7-man tablebases</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsModalOpen(true)}
            className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-bold font-display flex items-center gap-1 transition-all"
          >
            <Plus size={13} />
            <span>Custom FEN</span>
          </button>
        </div>
      </div>

      {/* Category Pills */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
        {['all', 'Pawn Endgames', 'Rook Endgames', 'Minor Piece', 'Queen Endgames'].map((cat) => {
          const isSelected = selectedCategory.toLowerCase() === cat.toLowerCase();
          return (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1 text-xs font-mono font-bold rounded-xl border transition-all whitespace-nowrap ${
                isSelected
                  ? 'bg-violet-500/25 border-violet-400 text-violet-200 shadow-sm'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              {cat === 'all' ? 'All Drills' : cat}
            </button>
          );
        })}
      </div>

      {/* Drills Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-[380px] overflow-y-auto pr-1">
        {filteredDrills.map((drill) => {
          const isActive = activeDrillId === drill.id;
          return (
            <div
              key={drill.id}
              className={`p-3.5 rounded-2xl border transition-all flex flex-col justify-between gap-2 text-left ${
                isActive
                  ? 'bg-gradient-to-r from-violet-500/25 to-indigo-600/15 border-violet-400 shadow-artisan'
                  : 'bg-slate-900/60 hover:bg-slate-800/80 border-slate-800'
              }`}
            >
              <div className="flex flex-col">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold font-display text-white">{drill.title}</span>
                  <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded-full bg-slate-950 text-amber-400 border border-slate-800">
                    Goal: {drill.goal.toUpperCase()}
                  </span>
                </div>
                <span className="text-[11px] text-slate-300 font-sans mt-1 line-clamp-2">
                  {drill.description}
                </span>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-800/60">
                <span className="text-[9px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                  {drill.category} • {drill.difficulty}
                </span>
                <div className="flex items-center gap-1.5">
                  {isActive ? (
                    <button
                      onClick={onStopDrill}
                      className="px-2.5 py-1 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-display font-bold text-[10px] transition-all"
                    >
                      Exit Drill
                    </button>
                  ) : (
                    <button
                      onClick={() => onStartDrill(drill.id)}
                      disabled={loading}
                      className="px-3 py-1 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-display font-bold text-[10px] shadow flex items-center gap-1 transition-all active:scale-95"
                    >
                      <PlayCircle size={12} />
                      <span>Start Drill</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Custom FEN Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[160] bg-black/75 backdrop-blur-md flex items-center justify-center p-4">
          <div className="glass-panel p-6 rounded-3xl max-w-md w-full flex flex-col gap-4 border-violet-500/40 shadow-artisan-lg animate-in zoom-in-95">
            <div className="flex items-center justify-between">
              <h4 className="text-base font-bold font-display text-white">Create Custom Endgame</h4>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-white">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateCustom} className="flex flex-col gap-3">
              <div className="flex flex-col gap-1 text-left">
                <label className="text-[10px] font-mono font-bold uppercase text-slate-400">Position FEN</label>
                <input
                  type="text"
                  required
                  value={fenInput}
                  onChange={(e) => setFenInput(e.target.value)}
                  placeholder="8/8/8/4k3/8/8/4K3/4R3 w - - 0 1"
                  className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-violet-400"
                />
              </div>

              <div className="flex flex-col gap-1 text-left">
                <label className="text-[10px] font-mono font-bold uppercase text-slate-400">Title</label>
                <input
                  type="text"
                  required
                  value={titleInput}
                  onChange={(e) => setTitleInput(e.target.value)}
                  placeholder="Lucena Bridge Position"
                  className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-sans text-white focus:outline-none focus:border-violet-400"
                />
              </div>

              <div className="grid grid-cols-2 gap-2 text-left">
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-mono font-bold uppercase text-slate-400">Target Goal</label>
                  <select
                    value={goalInput}
                    onChange={(e) => setGoalInput(e.target.value as 'win' | 'draw' | 'mate')}
                    className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-white"
                  >
                    <option value="win">Win Position</option>
                    <option value="draw">Hold Draw</option>
                    <option value="mate">Deliver Mate</option>
                  </select>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-mono font-bold uppercase text-slate-400">Player Color</label>
                  <select
                    value={colorInput}
                    onChange={(e) => setColorInput(e.target.value as 'white' | 'black')}
                    className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-white"
                  >
                    <option value="white">White</option>
                    <option value="black">Black</option>
                  </select>
                </div>
              </div>

              <div className="flex flex-col gap-1 text-left">
                <label className="text-[10px] font-mono font-bold uppercase text-slate-400">Description</label>
                <textarea
                  rows={2}
                  value={descInput}
                  onChange={(e) => setDescInput(e.target.value)}
                  placeholder="Key instructional takeaway..."
                  className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-sans text-white focus:outline-none focus:border-violet-400"
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-display font-bold text-xs shadow-md transition-all"
                >
                  Save &amp; Practice
                </button>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2.5 rounded-xl bg-slate-900 text-slate-300 text-xs font-mono"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
