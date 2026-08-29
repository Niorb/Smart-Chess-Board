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
