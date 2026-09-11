'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { ThemeMode, ResolvedTheme, ThemeContextValue } from './types';

export const THEME_STORAGE_KEY = 'fussion-theme';

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'dark';
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'dark';
  }
}

export const ThemeProvider: React.FC<{
  children: React.ReactNode;
  defaultTheme?: ThemeMode;
}> = ({ children, defaultTheme = 'system' }) => {
  const [theme, setThemeState] = useState<ThemeMode>(defaultTheme);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>('dark');
  const [mounted, setMounted] = useState(false);

  const applyTheme = useCallback((activeMode: ThemeMode) => {
    if (typeof window === 'undefined') return;

    const resolved = activeMode === 'system' ? getSystemTheme() : activeMode;
    setResolvedTheme(resolved);

    const root = document.documentElement;
    if (resolved === 'dark') {
      root.classList.add('dark');
      root.setAttribute('data-theme', 'dark');
      root.style.colorScheme = 'dark';
    } else {
      root.classList.remove('dark');
      root.setAttribute('data-theme', 'light');
      root.style.colorScheme = 'light';
    }
  }, []);

  // Initialize theme from localStorage on mount
  useEffect(() => {
    let initialMode = defaultTheme;
    try {
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      if (stored === 'light' || stored === 'dark' || stored === 'system') {
        initialMode = stored;
      }
    } catch {
      // ignore localStorage errors
    }

    setThemeState(initialMode);
    applyTheme(initialMode);
    setMounted(true);
  }, [defaultTheme, applyTheme]);

  // Listen to OS prefers-color-scheme changes when in system mode
  useEffect(() => {
    if (
      !mounted ||
      theme !== 'system' ||
      typeof window === 'undefined' ||
      typeof window.matchMedia !== 'function'
    ) {
      return;
    }

    try {
      const mql = window.matchMedia('(prefers-color-scheme: dark)');
      if (!mql) return;

      const handleChange = () => {
        applyTheme('system');
      };

      if (mql.addEventListener) {
        mql.addEventListener('change', handleChange);
        return () => mql.removeEventListener('change', handleChange);
      } else if (mql.addListener) {
        mql.addListener(handleChange);
        return () => mql.removeListener(handleChange);
      }
    } catch {
      // ignore media query listener errors
    }
  }, [mounted, theme, applyTheme]);

  const setTheme = useCallback(
    (newTheme: ThemeMode) => {
      setThemeState(newTheme);
      try {
        localStorage.setItem(THEME_STORAGE_KEY, newTheme);
      } catch {
        // ignore localStorage errors
      }
      applyTheme(newTheme);
    },
    [applyTheme]
  );

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
