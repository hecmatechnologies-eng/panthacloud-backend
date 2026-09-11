'use client';

import React from 'react';
import { HealthResponse, Project, User } from '@/lib/api';
import {
  Layers,
  Plus,
  CheckCircle2,
  XCircle,
  RefreshCw,
  LogOut,
  User as UserIcon,
} from 'lucide-react';

interface StudioHeaderProps {
  projects: Project[];
  selectedProjectId: string;
  onSelectProject: (id: string) => void;
  onOpenNewProject: () => void;
  health: HealthResponse | null;
  loadingHealth: boolean;
  onRefreshHealth: () => void;
  user?: User | null;
  onLogout?: () => void;
}

export const StudioHeader: React.FC<StudioHeaderProps> = ({
  projects,
  selectedProjectId,
  onSelectProject,
  onOpenNewProject,
  health,
  loadingHealth,
  onRefreshHealth,
  user,
  onLogout,
}) => {
  const isHealthy = health?.status === 'healthy';

  return (
    <header className="border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Left: Branding & Org Context */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-md shadow-indigo-950/50">
              <Layers className="w-4 h-4 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-white text-base tracking-tight">Fussion</span>
                <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-indigo-950/70 border border-indigo-800/60 text-indigo-300 font-semibold">
                  Studio
                </span>
              </div>
              <p className="text-[11px] text-zinc-400 font-normal leading-tight hidden sm:block">
                AI Integration Engineer
              </p>
            </div>
          </div>

          <div className="h-4 w-px bg-zinc-800" />

          {/* Project Selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-400 font-medium hidden md:inline">Project:</span>
            <select
              value={selectedProjectId}
              onChange={(e) => onSelectProject(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 text-xs font-semibold text-white rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-indigo-500 transition-colors"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <button
              onClick={onOpenNewProject}
              title="Create new project"
              className="p-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 hover:text-white rounded-lg text-xs transition-colors flex items-center gap-1 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span className="hidden lg:inline text-[11px] font-medium">New</span>
            </button>
          </div>
        </div>

        {/* Right: System Health, User Profile & Logout */}
        <div className="flex items-center gap-3">
          {/* Health status badge */}
          <div
            onClick={onRefreshHealth}
            className="flex items-center gap-2 px-2.5 py-1 bg-zinc-900/90 border border-zinc-800/80 rounded-full text-xs cursor-pointer hover:border-zinc-700 transition-colors"
            title="Click to refresh system health"
          >
            {loadingHealth ? (
              <RefreshCw className="w-3 h-3 text-zinc-400 animate-spin" />
            ) : isHealthy ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <XCircle className="w-3.5 h-3.5 text-rose-400" />
            )}
            <span className="font-mono text-[11px] text-zinc-300 hidden sm:inline">
              {isHealthy ? 'Operational' : 'System Degraded'}
            </span>
          </div>

          {/* User Profile & Logout if authenticated */}
          {user && (
            <>
              <div className="h-4 w-px bg-zinc-800 hidden sm:block" />

              <div className="flex items-center gap-2 text-xs">
                <div className="flex items-center gap-1.5 px-2.5 py-1 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-300">
                  <UserIcon className="w-3.5 h-3.5 text-indigo-400" />
                  <span className="max-w-[140px] truncate font-medium text-[11px]">
                    {user.full_name || user.email}
                  </span>
                </div>

                {onLogout && (
                  <button
                    onClick={onLogout}
                    title="Sign out of your workspace"
                    className="flex items-center gap-1.5 px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 hover:text-rose-300 hover:border-rose-900/60 rounded-lg text-[11px] font-medium transition-colors cursor-pointer"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span className="hidden md:inline">Sign Out</span>
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
