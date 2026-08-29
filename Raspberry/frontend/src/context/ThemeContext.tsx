import React, { useState, useEffect } from 'react';
import type { BoardThemeId, LensMode, StudioView } from '../types/theme';
import { ARTISAN_THEMES } from '../types/theme';
import { ThemeContext } from './ThemeContextDefinition';

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [themeId, setThemeIdState] = useState<BoardThemeId>(() => {
    const saved = localStorage.getItem('scb_artisan_theme');
    if (saved && saved in ARTISAN_THEMES) {
      return saved as BoardThemeId;
    }
    return 'birch_walnut';
  });

  const [lens, setLens] = useState<LensMode>(() => {
    const saved = localStorage.getItem('scb_lens_mode');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        // fallback
      }
    }
    return {
      aura: true,
      ledBezel: true,
      evalBar: true,
      hints: true,
    };
  });

  const [activeView, setActiveView] = useState<StudioView>('play');
  const [flipped, setFlipped] = useState<boolean>(false);

  useEffect(() => {
    localStorage.setItem('scb_artisan_theme', themeId);
  }, [themeId]);

  useEffect(() => {
    localStorage.setItem('scb_lens_mode', JSON.stringify(lens));
  }, [lens]);

  const setThemeId = (id: BoardThemeId) => {
    if (id in ARTISAN_THEMES) {
      setThemeIdState(id);
    }
  };

  const cycleTheme = () => {
    const themeKeys: BoardThemeId[] = ['birch_walnut', 'ink_bamboo', 'concrete_charcoal'];
    const currentIndex = themeKeys.indexOf(themeId);
    const nextTheme = themeKeys[(currentIndex + 1) % themeKeys.length];
    setThemeId(nextTheme);
  };

  const toggleLens = (key: keyof LensMode) => {
    setLens((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleOrientation = () => {
    setFlipped((prev) => !prev);
  };

  const currentTheme = ARTISAN_THEMES[themeId] || ARTISAN_THEMES.birch_walnut;

  return (
    <ThemeContext.Provider
      value={{
        themeId,
        currentTheme,
        setThemeId,
        cycleTheme,
        lens,
        setLens,
        toggleLens,
        activeView,
        setActiveView,
        flipped,
        setFlipped,
        toggleOrientation,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
};
