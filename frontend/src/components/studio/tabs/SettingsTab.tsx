'use client';

import React from 'react';
import { HealthResponse, Project } from '@/lib/api';
import { Settings, Server, Database, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';

interface SettingsTabProps {
  project: Project | undefined;
  health: HealthResponse | null;
  lastChecked: string;
}

export const SettingsTab: React.FC<SettingsTabProps> = ({
  project,
  health,
  lastChecked,
}) => {
  const isHealthy = health?.status === 'healthy';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-zinc-400" />
            <h1 className="text-lg font-bold text-white tracking-tight">Project &amp; System Settings</h1>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            Operational telemetry, database connectivity, and workspace environment configurations.
          </p>
        </div>
      </div>

      {/* System Health Section */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
        <h2 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
          <Server className="w-4 h-4 text-indigo-400" />
          Backend Operational Telemetry
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 space-y-1">
            <span className="text-[10px] text-zinc-400 font-mono block uppercase">Status</span>
            <div className="flex items-center gap-1.5">
              {isHealthy ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-400" />
              )}
              <span className="font-bold text-white">{health?.status || 'Unknown'}</span>
            </div>
          </div>

          <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 space-y-1">
            <span className="text-[10px] text-zinc-400 font-mono block uppercase">Service &amp; Version</span>
            <span className="font-mono text-white text-xs block truncate">
              {health?.service || 'fussion-backend'} ({health?.version || '0.1.0'})
            </span>
          </div>

          <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 space-y-1">
            <span className="text-[10px] text-zinc-400 font-mono block uppercase">Environment</span>
            <span className="font-mono text-white text-xs block capitalize">
              {health?.environment || 'development'}
            </span>
          </div>
        </div>

        {/* Database Health Card */}
        {health?.database && (
          <div className="bg-zinc-950 p-4 rounded-lg border border-zinc-800 flex items-center justify-between text-xs">
            <div className="flex items-center gap-3">
              <Database className="w-4 h-4 text-indigo-400" />
              <div>
                <span className="font-semibold text-white">Database Engine</span>
                <p className="text-[11px] text-zinc-400 font-mono">
                  Type: {health.database.type || 'postgresql'} • Latency: {health.database.latency_ms?.toFixed(2) || '0.50'} ms
                </p>
              </div>
            </div>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
              {health.database.status}
            </span>
          </div>
        )}
      </div>

      {/* Project Metadata Section */}
      {project && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
          <h2 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
            Project Configuration
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 space-y-1">
              <span className="text-[10px] text-zinc-400 block font-sans">Project Name</span>
              <span className="text-white font-bold">{project.name}</span>
            </div>

            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 space-y-1">
              <span className="text-[10px] text-zinc-400 block font-sans">Project Slug</span>
              <span className="text-indigo-300 font-bold">{project.slug}</span>
            </div>

            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 space-y-1 sm:col-span-2">
              <span className="text-[10px] text-zinc-400 block font-sans">Project ID</span>
              <span className="text-zinc-300 text-[11px]">{project.id}</span>
            </div>
          </div>
        </div>
      )}

      {/* Security Invariants Footer */}
      <div className="bg-zinc-950 border border-zinc-800/80 rounded-xl p-4 flex items-center justify-between text-xs text-zinc-400">
        <span className="flex items-center gap-1.5">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          Strict Multi-Tenant Containment: All resources scoped to parent organization.
        </span>
        <span className="font-mono text-[11px] text-zinc-400">
          Last checked: {lastChecked || 'Initial check'}
        </span>
      </div>
    </div>
  );
};
