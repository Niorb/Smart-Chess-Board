export type BoardThemeId = 'birch_walnut' | 'ink_bamboo' | 'concrete_charcoal';

export type StudioView = 'play' | 'academy' | 'analysis' | 'hardware';

export interface BoardTheme {
  id: BoardThemeId;
  name: string;
  label: string;
  description: string;
  light: string;
  dark: string;
  frame: string;
  borderAccent: string;
  lightText: string;
  darkText: string;
  checkGlow: string;
  lastMoveFrom: string;
  lastMoveTo: string;
}

export interface LensMode {
  aura: boolean;
  ledBezel: boolean;
  evalBar: boolean;
  hints: boolean;
}

export const ARTISAN_THEMES: Record<BoardThemeId, BoardTheme> = {
  birch_walnut: {
    id: 'birch_walnut',
    name: 'Scandinavian Birch & Walnut',
    label: 'Birch & Walnut',
    description: 'Natural organic woodwork with soft cream and deep amber walnut tones.',
    light: '#ecdab9',
    dark: '#9c6f44',
    frame: '#5c3a21',
    borderAccent: '#c99355',
    lightText: '#9c6f44',
    darkText: '#ecdab9',
    checkGlow: 'rgba(239, 68, 68, 0.75)',
    lastMoveFrom: 'rgba(245, 158, 11, 0.35)',
    lastMoveTo: 'rgba(245, 158, 11, 0.55)',
  },
  ink_bamboo: {
    id: 'ink_bamboo',
    name: 'Japanese Ink & Bamboo',
    label: 'Ink & Bamboo',
    description: 'Minimalist wabi-sabi aesthetic with washi paper light squares and sumi ink darks.',
    light: '#e8e2ce',
    dark: '#3e4a3d',
    frame: '#232b22',
    borderAccent: '#6b7d69',
    lightText: '#3e4a3d',
    darkText: '#e8e2ce',
    checkGlow: 'rgba(225, 29, 72, 0.75)',
    lastMoveFrom: 'rgba(16, 185, 129, 0.35)',
    lastMoveTo: 'rgba(16, 185, 129, 0.55)',
  },
  concrete_charcoal: {
    id: 'concrete_charcoal',
    name: 'Swiss Concrete & Matte Charcoal',
    label: 'Concrete & Charcoal',
    description: 'Clean architectural brutalism with stone gray and anodized slate squares.',
    light: '#d2d6dc',
    dark: '#4b5563',
    frame: '#1f2937',
    borderAccent: '#9ca3af',
    lightText: '#4b5563',
    darkText: '#d2d6dc',
    checkGlow: 'rgba(244, 63, 94, 0.75)',
    lastMoveFrom: 'rgba(6, 182, 212, 0.35)',
    lastMoveTo: 'rgba(6, 182, 212, 0.55)',
  },
};
