'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../context';
import { Layers, Loader2 } from 'lucide-react';

export interface ProtectedRouteProps {
  children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center p-4">
        <div className="flex flex-col items-center space-y-4 max-w-sm text-center">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-xl shadow-indigo-950/70 animate-pulse">
            <Layers className="w-6 h-6 text-white" />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-center gap-2 text-white font-bold text-sm tracking-tight">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
              <span>Authenticating Workspace...</span>
            </div>
            <p className="text-xs text-zinc-400 font-mono">
              Validating secure tenant session
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Return null while redirect is taking place
    return null;
  }

  return <>{children}</>;
};
