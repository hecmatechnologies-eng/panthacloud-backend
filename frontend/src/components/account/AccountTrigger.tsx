'use client';

import React, { useState } from 'react';
import { User } from '@/lib/api';
import { UserAvatar } from './UserAvatar';
import { AccountMenu } from './AccountMenu';
import { ChevronDown } from 'lucide-react';

export interface AccountTriggerProps {
  user?: User | null;
  onLogout?: () => void;
  className?: string;
}

export const AccountTrigger: React.FC<AccountTriggerProps> = ({
  user,
  onLogout,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Account menu"
        data-testid="account-menu-button"
        className="rounded-full p-1 transition-all cursor-pointer hover:bg-[var(--surface-elevated)] hover:ring-1 hover:ring-[var(--border)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-purple)] select-none flex items-center gap-1.5"
      >
        <UserAvatar user={user} size="sm" />
        <ChevronDown className="w-3.5 h-3.5 text-[var(--text-secondary)]" />
      </button>


      {/* Dropdown Menu */}
      <AccountMenu
        user={user}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onLogout={onLogout}
      />
    </div>
  );
};
