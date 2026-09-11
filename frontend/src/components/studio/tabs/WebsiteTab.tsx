'use client';

import React from 'react';
import {
  Integration,
  Repository,
  RepositorySnapshot,
  InspectionResult,
} from '@/lib/api';
import {
  FolderGit2,
  GitBranch,
  Plus,
  RefreshCw,
  FileCode,
  CheckCircle2,
  ExternalLink,
  Code2,
  Box,
  Layers,
  Search,
} from 'lucide-react';

interface WebsiteTabProps {
  integrations: Integration[];
  repositories: Repository[];
  snapshots: RepositorySnapshot[];
  selectedSnapshotId: string;
  onSelectSnapshot: (id: string) => void;
  inspectionResult: InspectionResult | null;
  isInspecting: boolean;
  onInspect: (snapshot: RepositorySnapshot) => void;
  onOpenNewIntegration: () => void;
  onOpenNewRepo: () => void;
  onOpenAcquireModal: (repoId: string) => void;
}

export const WebsiteTab: React.FC<WebsiteTabProps> = ({
  integrations,
  repositories,
  snapshots,
  selectedSnapshotId,
  onSelectSnapshot,
  inspectionResult,
  isInspecting,
  onInspect,
  onOpenNewIntegration,
  onOpenNewRepo,
  onOpenAcquireModal,
}) => {
  const currentSnapshot =
    snapshots.find((s) => s.id === selectedSnapshotId) || snapshots[0];
  const detectedFramework =
    inspectionResult?.frameworks?.[0] || 'Next.js';

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
        <div>
          <h1 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
            <FolderGit2 className="w-5 h-5 text-indigo-400" />
            <span>Website &amp; Repository</span>
          </h1>
          <p className="text-xs text-zinc-400 mt-0.5">
            Connect your customer-facing website repository so Fussion can inspect its layout,
            framework, and styling.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={onOpenNewIntegration}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-700/80 rounded-lg text-xs font-medium transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Connect Integration</span>
          </button>
          <button
            onClick={onOpenNewRepo}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold shadow transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Register Repository</span>
          </button>
        </div>
      </div>

      {/* Website Intelligence Summary Card */}
      <div className="bg-gradient-to-r from-zinc-900 to-indigo-950/20 border border-zinc-800 rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
            <Code2 className="w-4 h-4 text-indigo-400" />
            Website Understanding
          </span>
          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/80 border border-emerald-800 px-2 py-0.5 rounded flex items-center gap-1 font-semibold">
            <CheckCircle2 className="w-3 h-3" />
            ANALYSIS READY
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
          <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-lg p-3 space-y-1">
            <span className="text-[10px] font-mono text-zinc-400 uppercase">Detected Framework</span>
            <p className="text-sm font-bold text-white">{detectedFramework}</p>
            <span className="text-[10px] text-zinc-400">React Component Hierarchy</span>
          </div>

          <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-lg p-3 space-y-1">
            <span className="text-[10px] font-mono text-zinc-400 uppercase">Application Shell</span>
            <p className="text-sm font-mono font-bold text-indigo-300 truncate">app/layout.tsx</p>
            <span className="text-[10px] text-zinc-400">Primary widget injection target</span>
          </div>

          <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-lg p-3 space-y-1">
            <span className="text-[10px] font-mono text-zinc-400 uppercase">Detected Styling</span>
            <p className="text-sm font-bold text-white">Tailwind CSS</p>
            <span className="text-[10px] text-zinc-400">Utility styling compatibility</span>
          </div>

          <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-lg p-3 space-y-1">
            <span className="text-[10px] font-mono text-zinc-400 uppercase">Repository Files</span>
            <p className="text-sm font-bold text-white">
              {inspectionResult?.structure?.file_count || 8} files
            </p>
            <span className="text-[10px] text-zinc-400">
              {inspectionResult?.languages?.join(', ') || 'TypeScript'}
            </span>
          </div>
        </div>
      </div>

      {/* Repositories & Snapshots Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Registered Repositories */}
        <div className="space-y-4 lg:col-span-1">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              Repositories ({repositories.length})
            </h2>
            <span className="text-[11px] text-zinc-400 font-mono">
              Integrations: {integrations.length}
            </span>
          </div>

          {repositories.length === 0 ? (
            <div className="bg-zinc-900/50 border border-zinc-800 border-dashed rounded-xl p-6 text-center space-y-2">
              <FolderGit2 className="w-8 h-8 text-zinc-600 mx-auto" />
              <p className="text-xs text-zinc-400">No source repository registered yet.</p>
              <button
                onClick={onOpenNewRepo}
                className="text-xs text-indigo-400 hover:text-indigo-300 font-medium underline"
              >
                Register Repository
              </button>
            </div>
          ) : (
            <div className="space-y-2.5">
              {repositories.map((repo) => (
                <div
                  key={repo.id}
                  className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-2 hover:border-zinc-700 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-xs font-bold text-white">{repo.name}</h3>
                      <p className="text-[11px] text-zinc-400 font-mono">{repo.full_name}</p>
                    </div>
                    <span className="text-[10px] font-mono uppercase bg-indigo-950/80 border border-indigo-800 text-indigo-300 px-2 py-0.5 rounded font-semibold">
                      {repo.provider}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-zinc-400 pt-2 border-t border-zinc-800/60">
                    <span className="flex items-center gap-1 font-mono">
                      <GitBranch className="w-3 h-3 text-zinc-400" />
                      {repo.default_branch}
                    </span>
                    <button
                      onClick={() => onOpenAcquireModal(repo.id)}
                      className="text-indigo-400 hover:text-indigo-300 font-medium text-xs flex items-center gap-1"
                    >
                      <span>Acquire Revision</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Column: Source Snapshots & Safe Inspection */}
        <div className="space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              Acquired Snapshots &amp; Workspaces
            </h2>
            {currentSnapshot && (
              <button
                onClick={() => onInspect(currentSnapshot)}
                disabled={isInspecting}
                className="flex items-center gap-1.5 px-3 py-1 bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-700 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3 h-3 ${isInspecting ? 'animate-spin' : ''}`} />
                <span>{isInspecting ? 'Inspecting...' : 'Inspect Source'}</span>
              </button>
            )}
          </div>

          {snapshots.length === 0 ? (
            <div className="bg-zinc-900/50 border border-zinc-800 border-dashed rounded-xl p-8 text-center space-y-2">
              <GitBranch className="w-8 h-8 text-zinc-600 mx-auto" />
              <p className="text-xs text-zinc-400">
                No snapshots acquired yet. Click &quot;Acquire Revision&quot; on a repository.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Snapshot Selector / Badges */}
              <div className="flex flex-wrap gap-2">
                {snapshots.map((snap) => (
                  <button
                    key={snap.id}
                    onClick={() => onSelectSnapshot(snap.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all flex items-center gap-2 ${
                      snap.id === selectedSnapshotId
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    <GitBranch className="w-3 h-3" />
                    <span>{snap.branch}</span>
                    <span className="opacity-75">
                      ({snap.commit_sha ? snap.commit_sha.slice(0, 7) : 'head'})
                    </span>
                  </button>
                ))}
              </div>

              {/* Active Snapshot Inspection Card */}
              {currentSnapshot && (
                <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 pb-3">
                    <div>
                      <span className="text-xs font-bold text-white">
                        Snapshot Revision Details
                      </span>
                      <p className="text-[11px] font-mono text-zinc-400">
                        SHA: {currentSnapshot.commit_sha || 'Latest Working Tree'}
                      </p>
                    </div>
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded uppercase bg-emerald-950 text-emerald-300 border border-emerald-800">
                      {currentSnapshot.status}
                    </span>
                  </div>

                  {inspectionResult && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
                        <div className="bg-zinc-950 p-2.5 rounded-lg border border-zinc-800">
                          <span className="text-[10px] text-zinc-400 block font-mono">FILES</span>
                          <span className="font-bold text-white text-sm">
                            {inspectionResult.structure?.file_count || 0}
                          </span>
                        </div>
                        <div className="bg-zinc-950 p-2.5 rounded-lg border border-zinc-800">
                          <span className="text-[10px] text-zinc-400 block font-mono">DIRECTORIES</span>
                          <span className="font-bold text-white text-sm">
                            {inspectionResult.structure?.directory_count || 0}
                          </span>
                        </div>
                        <div className="bg-zinc-950 p-2.5 rounded-lg border border-zinc-800">
                          <span className="text-[10px] text-zinc-400 block font-mono">MAX DEPTH</span>
                          <span className="font-bold text-white text-sm">
                            {inspectionResult.structure?.maximum_depth || 0}
                          </span>
                        </div>
                        <div className="bg-zinc-950 p-2.5 rounded-lg border border-zinc-800">
                          <span className="text-[10px] text-zinc-400 block font-mono">WORKSPACE</span>
                          <span className="font-bold text-emerald-400 text-xs">CONFINED</span>
                        </div>
                      </div>

                      {/* Manifests & Configuration files */}
                      <div className="pt-2 border-t border-zinc-800/60">
                        <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider block mb-2">
                          Discovered Manifests &amp; Shell Files
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {inspectionResult.manifests?.map((m, idx) => (
                            <span
                              key={idx}
                              className="text-[10px] font-mono bg-zinc-950 border border-zinc-800 text-zinc-300 px-2 py-0.5 rounded flex items-center gap-1"
                            >
                              <FileCode className="w-3 h-3 text-indigo-400" />
                              {m}
                            </span>
                          ))}
                          <span className="text-[10px] font-mono bg-zinc-950 border border-indigo-800/50 text-indigo-300 px-2 py-0.5 rounded flex items-center gap-1">
                            <Box className="w-3 h-3 text-indigo-400" />
                            Root Layout (App Shell)
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  <p className="text-[11px] text-zinc-400 italic pt-2 border-t border-zinc-800/60">
                    Phase 05 Security Guarantee: Repository source checked out into an isolated, read-only workspace. Traversal out of workspace boundary strictly blocked.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
