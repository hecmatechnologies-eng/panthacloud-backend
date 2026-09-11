'use client';

import React, { useEffect, useRef } from 'react';
import { User } from '@/lib/api';
import { AccountIdentity } from './AccountIdentity';
import { ThemeSelector } from '@/components/theme';
import { UserRound as UserIcon, Settings, LogOut } from 'lucide-react';

export interface AccountMenuProps {
  user?: User | null;
  isOpen: boolean;
  onClose: () => void;
  onLogout?: () => void;
  className?: string;
}

export const AccountMenu: React.FC<AccountMenuProps> = ({
  user,
  isOpen,
  onClose,
  onLogout,
  className = '',
}) => {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label="Account options"
      data-testid="account-dropdown"
      className={`absolute right-0 mt-2 w-64 rounded-2xl bg-[var(--surface)] border border-[var(--border)] shadow-2xl backdrop-blur-md py-1 z-50 animate-in fade-in zoom-in-95 duration-100 transition-colors ${className}`}
    >
      {/* Identity Header */}
      <AccountIdentity user={user} />

      {/* Navigation Section */}
      <div className="p-1.5 space-y-0.5" role="none">
        {/* Profile */}
        <button
          type="button"
          role="menuitem"
          disabled
          className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)] rounded-xl transition-colors text-left select-none cursor-pointer"
        >
          <UserIcon className="w-4 h-4 text-[var(--text-secondary)]" />
          <span>Profile</span>
        </button>

        {/* Account settings */}
        <button
          type="button"
          role="menuitem"
          disabled
          className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)] rounded-xl transition-colors text-left select-none cursor-pointer"
        >
          <Settings className="w-4 h-4 text-[var(--text-secondary)]" />
          <span>Account settings</span>
        </button>

        {/* Appearance with Side Popup */}
        <ThemeSelector />
      </div>

      {/* Divider */}
      <div className="border-t border-[var(--border)]/70 my-1" role="separator" />

      {/* Sign Out Section */}
      <div className="p-1.5" role="none">
        {onLogout && (
          <button
            type="button"
            role="menuitem"
            data-testid="sign-out-button"
            onClick={() => {
              onClose();
              onLogout();
            }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-[#EF4444] hover:bg-red-500/10 dark:text-red-400 dark:hover:bg-red-950/30 rounded-xl transition-colors cursor-pointer text-left font-medium"
          >
            <LogOut className="w-4 h-4 text-[#EF4444] dark:text-red-400" />
            <span>Sign out</span>
          </button>
        )}
      </div>
    </div>
  );
};
