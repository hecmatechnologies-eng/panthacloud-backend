'use client';

import React from 'react';

export interface StudioWorkspaceProps {
  children?: React.ReactNode;
  className?: string;
}

export const StudioWorkspace: React.FC<StudioWorkspaceProps> = ({
  children,
  className = '',
}) => {
  return (
    <main
      data-testid="studio-workspace"
      className={`flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col ${className}`}
    >
      {children}
    </main>
  );
};
