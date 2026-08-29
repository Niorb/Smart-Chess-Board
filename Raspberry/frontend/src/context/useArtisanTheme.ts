import { useContext } from 'react';
import { ThemeContext, type ThemeContextType } from './ThemeContextDefinition';

export const useArtisanTheme = (): ThemeContextType => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useArtisanTheme must be used within a ThemeProvider');
  }
  return context;
};
