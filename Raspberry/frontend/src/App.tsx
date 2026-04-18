import { useState } from 'react'
import { useBoardState } from './hooks/useBoardState'
import { seekGame, cancelGame } from './api'
import { 
  Play, 
  XCircle, 
  Wifi, 
  WifiOff, 
  Grid3X3, 
  Cpu, 
  Settings,
  AlertTriangle
} from 'lucide-react'

function App() {
  const { state, isConnected } = useBoardState();
  const [loading, setLoading] = useState(false);

  const handleSeek = async () => {
    setLoading(true);
    try {
      await seekGame();
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

  // Helper to render the digital piece icons or characters
  const renderPiece = (p: string) => {
    if (p === '.') return null;
    const isWhite = p === p.toUpperCase();
    const piece = p.toLowerCase();
    
    // Simple mapping to Unicode chess pieces for now
    const icons: Record<string, string> = {
      p: isWhite ? '♙' : '♟',
      r: isWhite ? '♖' : '♜',
      n: isWhite ? '♘' : '♞',
      b: isWhite ? '♗' : '♝',
      q: isWhite ? '♕' : '♛',
      k: isWhite ? '♔' : '♚'
    };
    
    return (
      <span className={`text-4xl ${isWhite ? 'text-white' : 'text-slate-900'} drop-shadow-md select-none`}>
        {icons[piece] || p}
      </span>
    );
  };

  return (
    <div className="min-h-screen w-full bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Header / Status Bar */}
      <header className={`p-4 flex items-center justify-between border-b transition-colors duration-1000 ${
        state.status === 'SEEKING' ? 'border-blue-500/50 bg-blue-900/10' :
        state.status === 'PLAYING' ? 'border-green-500/50 bg-green-900/10' :
        'border-slate-800 bg-slate-900/50'
      }`}>
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-full ${isConnected ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
            {isConnected ? <Wifi size={20} /> : <WifiOff size={20} />}
          </div>
          <div>
            <h1 className="font-bold text-lg leading-tight">Smart Chess</h1>
            <p className="text-xs text-slate-400 uppercase tracking-widest font-semibold">
              {isConnected ? state.status : 'Disconnected'}
            </p>
          </div>
        </div>
        
        <div className="flex gap-2">
           <button className="p-2 text-slate-400 hover:text-white transition-colors">
              <Settings size={20} />
           </button>
        </div>
      </header>

      <main className="flex-1 p-4 flex flex-col items-center gap-6 max-w-md mx-auto w-full">
        
        {/* Main 8x8 Board Visualization */}
        <div className="relative w-full aspect-square bg-slate-800 rounded-xl overflow-hidden shadow-2xl border-4 border-slate-800">
          <div className="grid grid-cols-8 grid-rows-8 w-full h-full">
            {Array(8).fill(null).map((_, rIdx) => (
              Array(8).fill(null).map((_, cIdx) => {
                const isDark = (rIdx + cIdx) % 2 === 1;
                // Chess.com style rows: 7 (rank 8) at top, 0 (rank 1) at bottom
                const displayRow = 7 - rIdx;
                const piece = state.digital[displayRow]?.[cIdx] || '.';
                
                return (
                  <div 
                    key={`${rIdx}-${cIdx}`}
                    className={`flex items-center justify-center relative ${isDark ? 'bg-slate-700' : 'bg-slate-600'}`}
                  >
                    {renderPiece(piece)}
                  </div>
                );
              })
            ))}
          </div>

          {/* 4x4 Physical Overlay (Bottom Left) */}
          <div className="absolute bottom-0 left-0 w-1/2 h-1/2 bg-blue-500/10 border-2 border-blue-500/30 rounded-tr-2xl pointer-events-none backdrop-blur-[1px]">
             <div className="absolute -top-6 left-2 bg-blue-500/90 text-[10px] font-bold px-2 py-0.5 rounded-t uppercase tracking-tighter">
                Physical Sensors
             </div>
             <div className="grid grid-cols-4 grid-rows-4 w-full h-full p-1 gap-1">
                {Array(4).fill(null).map((_, rIdx) => (
                  Array(4).fill(null).map((_, cIdx) => {
                    const sensorRow = 3 - rIdx;
                    const isDetected = state.physical.grid?.[sensorRow]?.[cIdx];
                    return (
                      <div 
                        key={`sensor-${rIdx}-${cIdx}`}
                        className={`rounded-sm transition-all duration-300 ${
                          isDetected ? 'bg-green-400/80 shadow-[0_0_8px_rgba(74,222,128,0.5)]' : 'bg-slate-900/40'
                        }`}
                      />
                    );
                  })
                ))}
             </div>
          </div>
        </div>

        {/* Info & Alerts */}
        {state.status === 'SEEKING' && (
          <div className="w-full bg-blue-900/20 border border-blue-500/30 p-3 rounded-lg flex items-center gap-3 animate-pulse">
            <Grid3X3 className="text-blue-400 shrink-0" />
            <p className="text-sm text-blue-200">Looking for a match on Chess.com...</p>
          </div>
        )}

        {state.status === 'PLAYING' && state.my_color && (
          <div className="w-full bg-green-900/20 border border-green-500/30 p-3 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-3">
               <Cpu className="text-green-400 shrink-0" />
               <p className="text-sm text-green-200 uppercase font-bold tracking-widest">
                  Playing as {state.my_color}
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

        {/* Controls */}
        <div className="mt-auto w-full grid grid-cols-1 gap-3 pb-8">
          {state.status === 'IDLE' ? (
            <button 
              onClick={handleSeek}
              disabled={loading || !isConnected}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500 py-4 rounded-2xl font-bold text-lg flex items-center justify-center gap-2 transition-all active:scale-95 shadow-lg shadow-blue-900/20"
            >
              <Play size={24} fill="currentColor" />
              Seek Game (10 min)
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

      </main>

      <footer className="p-4 text-center border-t border-slate-900">
         <p className="text-[10px] text-slate-600 uppercase font-bold tracking-[0.2em]">
            Pi 4B Connected • Headless Engine v1.0
         </p>
      </footer>
    </div>
  )
}

export default App
