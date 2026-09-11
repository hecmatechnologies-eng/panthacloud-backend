import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  ThemeProvider,
  useTheme,
  ThemeSelector,
  THEME_STORAGE_KEY,
  themeTokens,
} from '@/components/theme';

// Test consumer helper component
const TestConsumer = () => {
  const { theme, resolvedTheme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="current-theme">{theme}</span>
      <span data-testid="resolved-theme">{resolvedTheme}</span>
      <button data-testid="set-light" onClick={() => setTheme('light')}>
        Light
      </button>
      <button data-testid="set-dark" onClick={() => setTheme('dark')}>
        Dark
      </button>
      <button data-testid="set-system" onClick={() => setTheme('system')}>
        System
      </button>
    </div>
  );
};

describe('Theme System (Tokens & Constants)', () => {
  it('defines valid tokens for both dark and light modes matching specifications', () => {
    expect(themeTokens.dark.canvas).toBe('#06100D');
    expect(themeTokens.dark.grid).toBe('#0F2A20');
    expect(themeTokens.dark.surface).toBe('#101816');
    expect(themeTokens.dark.purple).toBe('#7C3AED');
    expect(themeTokens.dark.success).toBe('#22C55E');

    expect(themeTokens.light.canvas).toBe('#F4F7F5');
    expect(themeTokens.light.grid).toBe('#D7E7DF');
    expect(themeTokens.light.surface).toBe('#FFFFFF');
    expect(themeTokens.light.purple).toBe('#7C3AED');
    expect(themeTokens.light.success).toBe('#16A34A');
  });
});

describe('ThemeProvider & useTheme Hook', () => {
  let matchMediaListeners: Array<(e: { matches: boolean }) => void> = [];
  let isDarkMode = true;

  beforeEach(() => {
    localStorage.clear();
    matchMediaListeners = [];
    isDarkMode = true;

    // Mock window.matchMedia
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('dark') ? isDarkMode : !isDarkMode,
      media: query,
      onchange: null,
      addListener: vi.fn((fn) => matchMediaListeners.push(fn)),
      removeListener: vi.fn(),
      addEventListener: vi.fn((_, fn) => matchMediaListeners.push(fn)),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.className = '';
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to system theme and resolves according to matchMedia', () => {
    isDarkMode = true;
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    );

    expect(screen.getByTestId('current-theme').textContent).toBe('system');
    expect(screen.getByTestId('resolved-theme').textContent).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('updates theme and document attributes when setTheme is called', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    );

    // Switch to Light
    fireEvent.click(screen.getByTestId('set-light'));
    expect(screen.getByTestId('current-theme').textContent).toBe('light');
    expect(screen.getByTestId('resolved-theme').textContent).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');

    // Switch to Dark
    fireEvent.click(screen.getByTestId('set-dark'));
    expect(screen.getByTestId('current-theme').textContent).toBe('dark');
    expect(screen.getByTestId('resolved-theme').textContent).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('restores theme from localStorage on initialization', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light');

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    );

    expect(screen.getByTestId('current-theme').textContent).toBe('light');
    expect(screen.getByTestId('resolved-theme').textContent).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('falls back safely to system if localStorage has invalid value', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'corrupted_theme_value');

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    );

    expect(screen.getByTestId('current-theme').textContent).toBe('system');
  });

  it('responds dynamically to system color scheme changes when in system mode', () => {
    isDarkMode = true;
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    );

    expect(screen.getByTestId('resolved-theme').textContent).toBe('dark');

    // Simulate OS switching to light
    isDarkMode = false;
    act(() => {
      matchMediaListeners.forEach((fn) => fn({ matches: false }));
    });

    expect(screen.getByTestId('resolved-theme').textContent).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('throws error when useTheme is called outside ThemeProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<TestConsumer />)).toThrow('useTheme must be used within a ThemeProvider');
    spy.mockRestore();
  });
});

describe('ThemeSelector Component', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders Appearance trigger with chevron right symbol', () => {
    render(
      <ThemeProvider defaultTheme="dark">
        <ThemeSelector />
      </ThemeProvider>
    );

    expect(screen.getByText('Appearance')).toBeDefined();
    expect(screen.getByTestId('appearance-toggle')).toBeDefined();
    expect(screen.queryByTestId('appearance-side-popup')).toBeNull();
  });

  it('opens side popup on click and allows selecting theme modes', () => {
    render(
      <ThemeProvider defaultTheme="dark">
        <ThemeSelector />
      </ThemeProvider>
    );

    const toggle = screen.getByTestId('appearance-toggle');
    fireEvent.click(toggle);

    // Options should now be visible in side popup
    expect(screen.getByTestId('appearance-side-popup')).toBeDefined();
    expect(screen.getByTestId('theme-option-light')).toBeDefined();
    expect(screen.getByTestId('theme-option-dark')).toBeDefined();
    expect(screen.getByTestId('theme-option-system')).toBeDefined();

    // Select Light
    fireEvent.click(screen.getByTestId('theme-option-light'));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');

    // Reopen side popup to select System
    fireEvent.click(toggle);
    expect(screen.getByTestId('appearance-side-popup')).toBeDefined();
    fireEvent.click(screen.getByTestId('theme-option-system'));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system');
  });
});
