'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/auth';
import { Layers, Loader2 } from 'lucide-react';

export default function RootPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading) {
      if (isAuthenticated) {
        router.replace('/studio');
      } else {
        router.replace('/login');
      }
    }
  }, [isAuthenticated, isLoading, router]);

  return (
    <div className="min-h-screen bg-black flex flex-col items-center justify-center p-4">
      <div className="flex flex-col items-center space-y-4 max-w-sm text-center">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-xl shadow-indigo-950/70 animate-pulse">
          <Layers className="w-6 h-6 text-white" />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-center gap-2 text-white font-bold text-sm tracking-tight">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
            <span>Connecting to Fussion Control Plane...</span>
          </div>
          <p className="text-xs text-zinc-400 font-mono">
            Resolving workspace routing
          </p>
        </div>
      </div>
    </div>
  );
}
