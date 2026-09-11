'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/auth';
import { StudioCanvas } from './StudioCanvas';
import { AppHeader } from './AppHeader';
import { StudioWorkspace } from './StudioWorkspace';

export interface AppShellProps {
  children?: React.ReactNode;
  className?: string;
  hideHeader?: boolean;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  className = '',
  hideHeader = false,
}) => {
  const router = useRouter();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  return (
    <StudioCanvas className={className}>
      {!hideHeader && <AppHeader user={user} onLogout={handleLogout} />}
      <StudioWorkspace>{children}</StudioWorkspace>
    </StudioCanvas>
  );
};
