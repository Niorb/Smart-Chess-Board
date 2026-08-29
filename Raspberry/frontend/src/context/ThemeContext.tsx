import React, { createContext, useContext, useState, useMemo, useCallback } from 'react';
import type { BoardThemeId, BoardTheme, StudioView, LensMode } from '../types/theme';

export const ARTISAN_THEMES: Record<BoardThemeId, BoardTheme> = {
  birch_walnut: {
    id: 'birch_walnut',
    name: 'birch_walnut',
    label: 'Nordic Birch & Walnut',
    description: 'Warm organic Nordic craft with golden birch and deep walnut squares',
    light: '#f5ecd7',
    dark: '#8b5e3c',
    frame: '#3d2516',
    borderAccent: '#d4af37',
    lightText: '#8b5e3c',
    darkText: '#f5ecd7',
    checkGlow: 'rgba(239, 68, 68, 0.85)',
    lastMoveFrom: 'rgba(245, 158, 11, 0.38)',
    lastMoveTo: 'rgba(245, 158, 11, 0.48)',
  },
  ink_bamboo: {
    id: 'ink_bamboo',
    name: 'ink_bamboo',
    label: 'Celadon Ink & Bamboo',
    description: 'Minimalist forest greens with muted bamboo and dark jade ink',
    light: '#e2ede4',
    dark: '#27443d',
    frame: '#13231f',
    borderAccent: '#5eead4',
    lightText: '#27443d',
    darkText: '#e2ede4',
    checkGlow: 'rgba(244, 63, 94, 0.85)',
    lastMoveFrom: 'rgba(94, 234, 212, 0.32)',
    lastMoveTo: 'rgba(94, 234, 212, 0.44)',
  },
  concrete_charcoal: {
    id: 'concrete_charcoal',
    name: 'concrete_charcoal',
    label: 'Nordic Concrete & Slate',
    description: 'Industrial studio aesthetics with crisp cool slate tones',
    light: '#e2e8f0',
    dark: '#334155',
    frame: '#0f172a',
    borderAccent: '#94a3b8',
    lightText: '#334155',
    darkText: '#e2e8f0',
    checkGlow: 'rgba(239, 68, 68, 0.85)',
    lastMoveFrom: 'rgba(139, 92, 246, 0.36)',
    lastMoveTo: 'rgba(139, 92, 246, 0.48)',
  },
};

interface ThemeContextType {
  themeId: BoardThemeId;
  currentTheme: BoardTheme;
  setThemeId: (id: BoardThemeId) => void;
  cycleTheme: () => void;
  lens: LensMode;
  toggleLens: (key: keyof LensMode) => void;
  setLens: (lens: Partial<LensMode>) => void;
  activeView: StudioView;
  setActiveView: (view: StudioView) => void;
  flipped: boolean;
  setFlipped: React.Dispatch<React.SetStateAction<boolean>>;
  toggleOrientation: () => void;
}

const THEME_STORAGE_KEY = 'scb_artisan_theme';
const LENS_STORAGE_KEY = 'scb_lens_modes';
const VIEW_STORAGE_KEY = 'scb_active_view';

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [themeId, setThemeIdState] = useState<BoardThemeId>(() => {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY) as BoardThemeId;
      if (saved && ARTISAN_THEMES[saved]) return saved;
      if ((saved as string) === 'green') return 'ink_bamboo';
      if ((saved as string) === 'wood') return 'birch_walnut';
      if ((saved as string) === 'slate') return 'concrete_charcoal';
    } catch {
      // fallback
    }
    return 'birch_walnut';
  });

  const [lens, setLensState] = useState<LensMode>(() => {
    try {
      const saved = localStorage.getItem(LENS_STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {
      // fallback
    }
    return {
      aura: true,
      ledBezel: true,
      evalBar: true,
      hints: true,
    };
  });

  const [activeView, setActiveViewState] = useState<StudioView>(() => {
    try {
      const saved = localStorage.getItem(VIEW_STORAGE_KEY) as StudioView;
      if (saved && ['play', 'academy', 'analysis', 'hardware'].includes(saved)) {
        return saved;
      }
    } catch {
      // fallback
    }
    return 'play';
  });

  const [flipped, setFlipped] = useState<boolean>(false);

  const setThemeId = useCallback((id: BoardThemeId) => {
    setThemeIdState(id);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const cycleTheme = useCallback(() => {
    const keys: BoardThemeId[] = ['birch_walnut', 'ink_bamboo', 'concrete_charcoal'];
    const currentIdx = keys.indexOf(themeId);
    const nextIdx = (currentIdx + 1) % keys.length;
    setThemeId(keys[nextIdx]);
  }, [themeId, setThemeId]);

  const toggleLens = useCallback((key: keyof LensMode) => {
    setLensState((prev) => {
      const updated = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(LENS_STORAGE_KEY, JSON.stringify(updated));
      } catch {
        /* ignore */
      }
      return updated;
    });
  }, []);

  const setLens = useCallback((partial: Partial<LensMode>) => {
    setLensState((prev) => {
      const updated = { ...prev, ...partial };
      try {
        localStorage.setItem(LENS_STORAGE_KEY, JSON.stringify(updated));
      } catch {
        /* ignore */
      }
      return updated;
    });
  }, []);

  const setActiveView = useCallback((view: StudioView) => {
    setActiveViewState(view);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, view);
    } catch {
      /* ignore */
    }
  }, []);

  const toggleOrientation = useCallback(() => {
    setFlipped((prev) => !prev);
  }, []);

  const currentTheme = useMemo(() => ARTISAN_THEMES[themeId] || ARTISAN_THEMES.birch_walnut, [themeId]);

  const value = useMemo(
    () => ({
      themeId,
      currentTheme,
      setThemeId,
      cycleTheme,
      lens,
      toggleLens,
      setLens,
      activeView,
      setActiveView,
      flipped,
      setFlipped,
      toggleOrientation,
    }),
    [themeId, currentTheme, setThemeId, cycleTheme, lens, toggleLens, setLens, activeView, setActiveView, flipped, toggleOrientation]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useArtisanTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useArtisanTheme must be used within a ThemeProvider');
  }
  return context;
};
