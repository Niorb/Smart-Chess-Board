import React, { useEffect } from 'react';
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  title?: string;
  message: string;
  duration?: number;
}

interface ToastNotificationProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const ToastNotification: React.FC<ToastNotificationProps> = ({ toasts, onDismiss }) => {
  return (
    <div className="fixed bottom-5 right-5 z-[200] flex flex-col gap-2 pointer-events-none max-w-sm w-full px-4">
      {toasts.map((toast) => {
        return (
          <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
        );
      })}
    </div>
  );
};

const ToastItem: React.FC<{ toast: ToastMessage; onDismiss: (id: string) => void }> = ({ toast, onDismiss }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, toast.duration || 4500);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  const borderClass =
    toast.type === 'success' ? 'border-emerald-500/50 bg-emerald-950/80 text-emerald-100 shadow-emerald-glow' :
    toast.type === 'error' ? 'border-rose-500/50 bg-rose-950/80 text-rose-100 shadow-rose-glow' :
    toast.type === 'warning' ? 'border-amber-500/50 bg-amber-950/80 text-amber-100 shadow-amber-glow' :
    'border-cyan-500/50 bg-cyan-950/80 text-cyan-100 shadow-cyan-glow';

  const icon =
    toast.type === 'success' ? <CheckCircle2 size={18} className="text-emerald-400 shrink-0 mt-0.5" /> :
    toast.type === 'error' ? <AlertTriangle size={18} className="text-rose-400 shrink-0 mt-0.5" /> :
    toast.type === 'warning' ? <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" /> :
    <Info size={18} className="text-cyan-400 shrink-0 mt-0.5" />;

  return (
    <div className={`pointer-events-auto flex items-start gap-3 p-3.5 rounded-2xl border backdrop-blur-xl transition-all duration-300 shadow-xl animate-in slide-in-from-bottom-5 ${borderClass}`}>
      {icon}
      <div className="flex-1 flex flex-col text-left">
        {toast.title && <span className="font-bold text-xs font-display">{toast.title}</span>}
        <span className="text-[11px] opacity-90 leading-tight font-sans">{toast.message}</span>
      </div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="text-slate-400 hover:text-white transition-colors"
      >
        <X size={14} />
      </button>
    </div>
  );
};
