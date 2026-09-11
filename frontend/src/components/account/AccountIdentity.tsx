'use client';

import React from 'react';
import { User } from '@/lib/api';
import { UserAvatar } from './UserAvatar';

export interface AccountIdentityProps {
  user?: User | null;
  className?: string;
}

export const AccountIdentity: React.FC<AccountIdentityProps> = ({ user, className = '' }) => {
  const displayName =
    user?.profile?.displayName || user?.full_name || 'Abel Byamukama';
  const email = user?.email || 'abel@example.com';

  return (
    <div
      data-testid="account-identity"
      className={`px-4 py-3.5 flex items-center gap-3 border-b border-[var(--border)]/70 ${className}`}
    >
      <UserAvatar user={user} size="md" />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
          {displayName}
        </p>
        <p className="text-xs text-[var(--text-secondary)] truncate">
          {email}
        </p>
      </div>
    </div>
  );
};
