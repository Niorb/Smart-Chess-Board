import { createContext } from 'react';
import type { BoardThemeId, BoardTheme, LensMode, StudioView } from '../types/theme';

export interface ThemeContextType {
  themeId: BoardThemeId;
  currentTheme: BoardTheme;
  setThemeId: (id: BoardThemeId) => void;
  cycleTheme: () => void;
  lens: LensMode;
  setLens: React.Dispatch<React.SetStateAction<LensMode>>;
  toggleLens: (key: keyof LensMode) => void;
  activeView: StudioView;
  setActiveView: (view: StudioView) => void;
  flipped: boolean;
  setFlipped: (flipped: boolean) => void;
  toggleOrientation: () => void;
}

export const ThemeContext = createContext<ThemeContextType | undefined>(undefined);
