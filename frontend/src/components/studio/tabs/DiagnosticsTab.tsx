'use client';

import React, { useState } from 'react';
import { DiscoveryRun, RepositorySnapshot } from '@/lib/api';
import { Activity, Route, RefreshCw } from 'lucide-react';

interface DiagnosticsTabProps {
  selectedSnapshotId: string;
  snapshots: RepositorySnapshot[];
  selectedDiscovery: DiscoveryRun | null;
  isRunningDiscovery: boolean;
  onRunDiscovery: (snap: RepositorySnapshot) => void;
}

export const DiagnosticsTab: React.FC<DiagnosticsTabProps> = ({
  selectedSnapshotId,
  snapshots,
  selectedDiscovery,
  isRunningDiscovery,
  onRunDiscovery,
}) => {
  // Discovery internal sub-tabs
  const [activeDiscTab, setActiveDiscTab] = useState<
    'overview' | 'frameworks' | 'entrypoints' | 'routes' | 'dependencies'
  >('overview');

  const currentSnapshot = snapshots.find((s) => s.id === selectedSnapshotId);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-amber-400" />
            <h1 className="text-lg font-bold text-white tracking-tight">
              Technical Details &amp; Engineering Diagnostics
            </h1>
            <span className="text-[10px] font-mono uppercase bg-amber-950/80 border border-amber-800 text-amber-300 px-2 py-0.5 rounded font-semibold">
              Post-MVP / Diagnostic Tooling
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            Low-level repository AST inspection and deterministic architecture discovery.
          </p>
        </div>
      </div>

      {/* Section label */}
      <div className="flex items-center gap-2 border-b border-zinc-800 pb-2 text-xs">
        <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium bg-zinc-800 text-white border border-zinc-700">
          <Route className="w-3.5 h-3.5" />
          <span>Architecture Discovery</span>
        </span>
      </div>

      {/* SECTION 1: ARCHITECTURE DISCOVERY */}
      <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
          <div>
            <h2 className="text-sm font-semibold text-white">Static Architecture Discovery</h2>
            <p className="text-xs text-zinc-400">
              AST parsing, entrypoint detection, routes, and dependency manifests.
            </p>
          </div>
          {currentSnapshot && (
            <button
              onClick={() => onRunDiscovery(currentSnapshot)}
              disabled={isRunningDiscovery}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600/90 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold shadow transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRunningDiscovery ? 'animate-spin' : ''}`} />
              <span>{isRunningDiscovery ? 'Discovering...' : 'Run Discovery'}</span>
            </button>
          )}
        </div>

        {selectedDiscovery && (
          <div className="space-y-4">
            {/* Internal Tab Bar */}
            <div className="flex items-center gap-2 border-b border-zinc-800 pb-2 text-xs font-mono">
              {(['overview', 'frameworks', 'entrypoints', 'routes', 'dependencies'] as const).map(
                (tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveDiscTab(tab)}
                    className={`px-2.5 py-1 rounded uppercase ${
                      activeDiscTab === tab
                        ? 'bg-zinc-800 text-indigo-300 font-bold'
                        : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    {tab}
                  </button>
                )
              )}
            </div>

            {activeDiscTab === 'overview' && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg">
                  <span className="text-zinc-400 block text-[10px]">FRAMEWORKS</span>
                  <span className="text-white font-bold text-sm">
                    {selectedDiscovery.metadata.frameworks?.length || 0}
                  </span>
                </div>
                <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg">
                  <span className="text-zinc-400 block text-[10px]">ROUTES</span>
                  <span className="text-white font-bold text-sm">
                    {selectedDiscovery.metadata.routes?.length || 0}
                  </span>
                </div>
                <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg">
                  <span className="text-zinc-400 block text-[10px]">DEPENDENCIES</span>
                  <span className="text-white font-bold text-sm">
                    {selectedDiscovery.metadata.dependencies?.length || 0}
                  </span>
                </div>
                <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg">
                  <span className="text-zinc-400 block text-[10px]">ENTRYPOINTS</span>
                  <span className="text-white font-bold text-sm">
                    {selectedDiscovery.metadata.entrypoints?.length || 0}
                  </span>
                </div>
              </div>
            )}

            {activeDiscTab === 'frameworks' && (
              <div className="space-y-2 text-xs">
                {selectedDiscovery.metadata.frameworks?.map((fw, idx) => (
                  <div
                    key={idx}
                    className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg flex items-center justify-between"
                  >
                    <span className="font-bold text-white">{fw.name}</span>
                    <span className="font-mono text-zinc-400">{fw.version || 'detected'}</span>
                  </div>
                ))}
              </div>
            )}

            {activeDiscTab === 'entrypoints' && (
              <div className="space-y-2 text-xs font-mono">
                {selectedDiscovery.metadata.entrypoints?.map((ep, idx) => (
                  <div
                    key={idx}
                    className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg flex items-center justify-between"
                  >
                    <span className="text-indigo-300 font-bold">{ep.path}</span>
                    <span className="text-zinc-400">{ep.framework}</span>
                  </div>
                ))}
              </div>
            )}

            {activeDiscTab === 'routes' && (
              <div className="space-y-2 text-xs font-mono">
                {selectedDiscovery.metadata.routes?.map((r, idx) => (
                  <div
                    key={idx}
                    className="bg-zinc-900 border border-zinc-800 p-2.5 rounded-lg flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-emerald-400 font-bold">{r.method}</span>
                      <span className="text-white">{r.path}</span>
                    </div>
                    <span className="text-zinc-500 text-[11px]">{r.source_file}</span>
                  </div>
                ))}
              </div>
            )}

            {activeDiscTab === 'dependencies' && (
              <div className="space-y-1.5 text-xs font-mono">
                {selectedDiscovery.metadata.dependencies?.map((dep, idx) => (
                  <div
                    key={idx}
                    className="bg-zinc-900 border border-zinc-800 p-2 rounded flex items-center justify-between"
                  >
                    <span className="text-white">{dep.name}</span>
                    <span className="text-zinc-400">{dep.version_spec}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
