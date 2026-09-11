'use client';

import React from 'react';
import { User } from '@/lib/api';
import { Layers, Bell } from 'lucide-react';
import { AccountTrigger } from '@/components/account';
import { ProjectSelector } from '@/features/project';

export interface AppHeaderProps {
  user?: User | null;
  onLogout?: () => void;
  className?: string;
}

export const AppHeader: React.FC<AppHeaderProps> = ({ user, onLogout, className = '' }) => {
  return (
    <header
      data-testid="studio-header"
      className={`sticky top-0 z-40 w-full bg-transparent border-b border-[var(--border)] backdrop-blur-sm transition-colors duration-150 ${className}`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Left: Fussion Branding & Contextual Project Selector */}
        <div className="flex items-center gap-3 select-none">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center shadow-sm">
              <Layers className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-[var(--text-primary)] text-base tracking-tight transition-colors">
              Fussion
            </span>
          </div>

          {/* Project Selector (mounts when active project exists) */}
          <ProjectSelector />
        </div>

        {/* Right: Notifications and Floating Account / Profile Affordance */}
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            data-testid="notification-bell-button"
            aria-label="Notifications"
            className="relative p-2 rounded-full text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)] transition-colors cursor-pointer"
          >
            <Bell className="w-4 h-4" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[var(--color-purple)] ring-2 ring-[var(--surface)]" />
          </button>

          <AccountTrigger user={user} onLogout={onLogout} />
        </div>
      </div>
    </header>
  );
};

