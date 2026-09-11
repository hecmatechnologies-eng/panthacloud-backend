'use client';

import React, { useState } from 'react';
import { User } from '@/lib/api';
import { UserRound as UserIcon } from 'lucide-react';

export interface UserAvatarProps {
  user?: User | null;
  avatarUrl?: string | null;
  displayName?: string | null;
  email?: string | null;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  alt?: string;
}

export function extractInitials(nameOrEmail?: string | null): string {
  if (!nameOrEmail) return '';
  const trimmed = nameOrEmail.trim();
  if (trimmed.includes('@')) {
    const localPart = trimmed.split('@')[0];
    return localPart ? localPart[0].toUpperCase() : '';
  }
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return '';
}

const sizeClasses = {
  sm: 'w-8 h-8 text-xs font-semibold',
  md: 'w-10 h-10 text-sm font-semibold',
  lg: 'w-16 h-16 text-xl font-bold',
};

const iconSizes = {
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-8 h-8',
};

export const UserAvatar: React.FC<UserAvatarProps> = ({
  user,
  avatarUrl,
  displayName,
  email,
  size = 'sm',
  className = '',
  alt,
}) => {
  const [imageError, setImageError] = useState(false);

  const effectiveAvatarUrl = avatarUrl ?? user?.profile?.avatarUrl ?? null;
  const effectiveDisplayName =
    displayName ?? user?.profile?.displayName ?? user?.full_name ?? null;
  const effectiveEmail = email ?? user?.email ?? null;

  const initials = extractInitials(effectiveDisplayName || effectiveEmail);
  const accessibleLabel =
    alt || effectiveDisplayName || effectiveEmail || 'User Avatar';

  // State A: Valid image URL exists and hasn't errored
  if (effectiveAvatarUrl && !imageError) {
    return (
      <div
        data-testid="user-avatar"
        className={`relative inline-flex items-center justify-center shrink-0 rounded-full overflow-hidden border border-[var(--border)] bg-[var(--surface)] ${sizeClasses[size]} ${className}`}
      >
        <img
          src={effectiveAvatarUrl}
          alt={accessibleLabel}
          onError={() => setImageError(true)}
          className="w-full h-full object-cover rounded-full"
        />
      </div>
    );
  }

  // State B: Initials generated from name or email (matching purple avatar in reference)
  if (initials) {
    return (
      <div
        data-testid="user-avatar"
        className={`inline-flex items-center justify-center shrink-0 rounded-full bg-gradient-to-tr from-[#6D28D9] to-[#7C3AED] text-white font-semibold select-none shadow-sm ${sizeClasses[size]} ${className}`}
        aria-label={accessibleLabel}
        role="img"
      >
        <span>{initials}</span>
      </div>
    );
  }

  // State C: Generic person fallback icon
  return (
    <div
      data-testid="user-avatar"
      className={`inline-flex items-center justify-center shrink-0 rounded-full border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--text-secondary)] select-none shadow-sm ${sizeClasses[size]} ${className}`}
      aria-label={accessibleLabel}
      role="img"
    >
      <UserIcon className={iconSizes[size]} />
    </div>
  );
};
