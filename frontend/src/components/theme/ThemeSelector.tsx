'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useTheme } from './ThemeContext';
import { ThemeMode } from './types';
import { Sun, Moon, Monitor, ChevronRight, Check } from 'lucide-react';

export interface ThemeSelectorProps {
  className?: string;
}

const themeOptions: { mode: ThemeMode; label: string; icon: React.FC<{ className?: string }> }[] = [
  { mode: 'light', label: 'Light', icon: Sun },
  { mode: 'dark', label: 'Dark', icon: Moon },
  { mode: 'system', label: 'System', icon: Monitor },
];

export const ThemeSelector: React.FC<ThemeSelectorProps> = ({ className = '' }) => {
  const { theme, setTheme } = useTheme();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close side popup when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Primary Row: Appearance item with '>' chevron */}
      <button
        type="button"
        role="menuitem"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Appearance options"
        data-testid="appearance-toggle"
        onClick={() => setIsOpen(!isOpen)}
        onMouseEnter={() => setIsOpen(true)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)] rounded-xl transition-colors text-left cursor-pointer group"
      >
        <div className="flex items-center gap-2.5">
          <Sun className="w-4 h-4 text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors" />
          <span>Appearance</span>
        </div>

        <ChevronRight className="w-3.5 h-3.5 text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-transform" />
      </button>

      {/* Side Popup Flyout Menu (Appears to the left of Appearance item) */}
      {isOpen && (
        <div
          role="menu"
          aria-label="Theme options"
          data-testid="appearance-side-popup"
          data-test-options="appearance-options"
          onMouseLeave={() => setIsOpen(false)}
          className="absolute right-full top-0 mr-2 w-44 rounded-2xl bg-[var(--surface)] border border-[var(--border)] shadow-2xl p-1.5 z-50 animate-in fade-in slide-in-from-right-2 duration-150 transition-colors"
        >
          <div className="px-2 py-1 text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider select-none">
            Theme
          </div>

          <div className="space-y-0.5" data-testid="appearance-options">
            {themeOptions.map(({ mode, label, icon: Icon }) => {
              const isSelected = theme === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  role="menuitem"
                  data-testid={`theme-option-${mode}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setTheme(mode);
                    setIsOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 text-xs rounded-xl transition-colors cursor-pointer text-left ${
                    isSelected
                      ? 'text-[var(--color-purple)] font-medium bg-[var(--color-purple)]/10'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)]'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Icon className="w-3.5 h-3.5" />
                    <span>{label}</span>
                  </div>
                  {isSelected && <Check className="w-3.5 h-3.5 text-[var(--color-purple)]" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
