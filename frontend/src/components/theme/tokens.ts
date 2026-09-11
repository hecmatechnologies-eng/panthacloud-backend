export interface ThemeTokens {
  canvas: string;
  grid: string;
  surface: string;
  surfaceElevated: string;
  border: string;
  textPrimary: string;
  textSecondary: string;
  purple: string;
  success: string;
}

export const themeTokens: Record<'dark' | 'light', ThemeTokens> = {
  dark: {
    canvas: '#06100D',
    grid: '#0F2A20',
    surface: '#101816',
    surfaceElevated: '#151F1B',
    border: '#1F3A31',
    textPrimary: '#F8FAF9',
    textSecondary: '#94A3A0',
    purple: '#7C3AED',
    success: '#22C55E',
  },
  light: {
    canvas: '#F4F7F5',
    grid: '#D7E7DF',
    surface: '#FFFFFF',
    surfaceElevated: '#F8FAF9',
    border: '#E5E7EB',
    textPrimary: '#0F172A',
    textSecondary: '#64748B',
    purple: '#7C3AED',
    success: '#16A34A',
  },
};
