'use client';

import React, { useState } from 'react';
import { useProject } from '../context';
import { useWebsiteStage } from '../hooks/useWebsiteStage';
import { Project } from '@/lib/api';
import { GitHubRepositoryRead } from '@/lib/api/github';
import {
  FolderGit2,
  GitBranch,
  ArrowLeft,
  CheckCircle2,
  ArrowRight,
  ExternalLink,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  Sparkles,
  ScanSearch,
  Lock,
} from 'lucide-react';

export interface WebsiteStageViewProps {
  project: Project;
  className?: string;
}

export const WebsiteStageView: React.FC<WebsiteStageViewProps> = ({
  project,
  className = '',
}) => {
  const { activeOrg, setActiveItem, markStageCompleted, isStageCompleted } = useProject();
  const orgId = project.organization_id || activeOrg?.id;

  const handleStatusChange = React.useCallback(
    (isCompleted: boolean) => {
      if (isStageCompleted('website') !== isCompleted) {
        markStageCompleted('website', isCompleted);
      }
    },
    [markStageCompleted, isStageCompleted]
  );

  const {
    config,
    analysis,
    installations,
    repositories,
    isLoading,
    isConnecting,
    isDisconnecting,
    isAnalyzing,
    isSelecting,
    isLoadingRepositories,
    isConnectingGitHub,
    error,
    disconnect,
    analyze,
    selectTarget,
    startGitHubInstall,
    connectRepository,
    clearError,
  } = useWebsiteStage({
    orgId,
    projectId: project.id,
    onStatusChange: handleStatusChange,
  });

  const [repoQuery, setRepoQuery] = useState('');

  const handleConnectGitHub = async () => {
    try {
      const url = await startGitHubInstall();
      window.location.href = url;
    } catch {
      // Error handled by hook
    }
  };

  const handleSelectRepo = async (repo: GitHubRepositoryRead) => {
    try {
      await connectRepository(repo);
    } catch {
      // Error handled by hook
    }
  };

  const handleAnalyze = async () => {
    try {
      await analyze();
    } catch {
      // Error handled by hook
    }
  };

  const handleSelectTarget = async (path: string) => {
    try {
      await selectTarget(path, analysis?.framework_skill_id ?? null);
    } catch {
      // Error handled by hook
    }
  };

  const isConnected = config?.status === 'CONNECTED';
  const topCandidate = analysis?.integration_candidates?.[0];
  const filteredRepositories = repositories.filter((repo) =>
    repo.full_name.toLowerCase().includes(repoQuery.trim().toLowerCase())
  );

  return (
    <div
      data-testid="website-stage-view"
      className={`flex-1 w-full max-w-3xl py-4 space-y-6 text-left transition-colors duration-150 ${className}`}
    >
      {/* Back to Overview */}
      <div>
        <button
          type="button"
          onClick={() => setActiveItem('overview')}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer group"
        >
          <ArrowLeft className="w-3.5 h-3.5 transition-transform group-hover:-translate-x-0.5" />
          <span>Back to Overview</span>
        </button>
      </div>

      {/* Stage Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold uppercase tracking-wider bg-purple-100/80 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40">
            BUILD · Stage 1 of 5
          </span>
          {isConnected && (
            <span
              data-testid="website-connected-badge"
              className="flex items-center gap-1 text-[11px] font-mono text-emerald-600 dark:text-emerald-400 font-medium"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Connected</span>
            </span>
          )}
        </div>

        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--text-primary)] transition-colors">
          Website Connection
        </h2>

        <p className="text-xs sm:text-sm text-[var(--text-secondary)] transition-colors leading-relaxed max-w-2xl">
          Connect your customer-facing website repository so Fussion can understand your framework and ground your assistant.
        </p>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="p-8 rounded-2xl bg-[var(--surface)] border border-[var(--border)] shadow-xs flex items-center justify-center gap-2.5 text-xs text-[var(--text-muted)] font-mono">
          <RefreshCw className="w-4 h-4 animate-spin text-[var(--color-purple)]" />
          <span>Checking website connection status...</span>
        </div>
      )}

      {/* Error Alert */}
      {!isLoading && error && (
        <div
          data-testid="website-error-banner"
          className="flex items-center justify-between p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs shadow-xs"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={clearError}
            className="text-[11px] font-mono underline hover:no-underline cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* STATE C: Configured Studio Stage */}
      {!isLoading && isConnected && config && (
        <div data-testid="website-connected-panel" className="space-y-6">
          {/* Main Connected Details Surface */}
          <div className="rounded-3xl bg-[var(--surface)] border border-[var(--border)] shadow-xs p-6 sm:p-7 space-y-6">
            {/* Header / Repo info */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)]/70 pb-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-purple-50 text-purple-600 dark:bg-purple-950/60 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40 flex items-center justify-center shrink-0">
                  <FolderGit2 className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3
                      data-testid="connected-repo-name"
                      className="text-sm sm:text-base font-bold text-[var(--text-primary)] font-mono"
                    >
                      {config.repository_owner}/{config.repository_name}
                    </h3>
                    <a
                      href={`https://github.com/${config.repository_owner}/${config.repository_name}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                      title="Open on GitHub"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] font-mono text-[var(--text-muted)] mt-0.5">
                    <GitBranch className="w-3 h-3" />
                    <span>Default branch: {config.default_branch}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-mono font-medium self-start sm:self-center">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Verified Source</span>
              </div>
            </div>

            {/* Grid Attributes */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3.5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)]/80 space-y-1">
                <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider">
                  Framework
                </span>
                <p
                  data-testid="detected-framework"
                  className="text-xs font-semibold text-[var(--text-primary)] font-mono truncate"
                >
                  {analysis?.framework_skill_id || config.framework_skill_id || 'Not detected'}
                </p>
              </div>

              <div className="p-3.5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)]/80 space-y-1">
                <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider">
                  Integration Point
                </span>
                <p
                  data-testid="detected-target"
                  className="text-xs font-semibold font-mono text-[var(--text-primary)] truncate"
                >
                  {topCandidate?.path || config.widget_target_path}
                </p>
              </div>

              <div className="p-3.5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)]/80 space-y-1">
                <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider">
                  Security Vault
                </span>
                <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Credentials Encrypted</span>
                </p>
              </div>
            </div>

            {/* Analysis Surface */}
            <div
              data-testid="website-analysis-panel"
              className="p-5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)]/80 space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                    <ScanSearch className="w-3.5 h-3.5 text-[var(--color-purple)]" />
                    <span>Repository Analysis</span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                    {analysis
                      ? 'Detected from the repository at a pinned commit.'
                      : 'Run the analyst to detect the framework, app shell and integration point.'}
                  </p>
                </div>
                <button
                  type="button"
                  data-testid="analyze-website-button"
                  onClick={handleAnalyze}
                  disabled={isAnalyzing}
                  className="px-4 py-2.5 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white text-xs font-medium shadow-xs transition-all cursor-pointer flex items-center justify-center gap-1.5 shrink-0 disabled:opacity-50"
                >
                  {isAnalyzing ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Analysing...</span>
                    </>
                  ) : (
                    <>
                      <ScanSearch className="w-3.5 h-3.5" />
                      <span>{analysis ? 'Re-run Analysis' : 'Analyze Repository'}</span>
                    </>
                  )}
                </button>
              </div>

              {analysis?.unsupported_reason && (
                <div
                  data-testid="analysis-unsupported"
                  className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs"
                >
                  {analysis.unsupported_reason}
                </div>
              )}

              {analysis && !analysis.unsupported_reason && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[
                      ['Router', analysis.router],
                      ['Language', analysis.language],
                      ['Package Manager', analysis.package_manager],
                      ['Build Command', analysis.build_command],
                    ].map(([label, value]) => (
                      <div key={label} className="space-y-1">
                        <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider">
                          {label}
                        </span>
                        <p className="text-xs font-mono text-[var(--text-primary)] truncate">
                          {value || '—'}
                        </p>
                      </div>
                    ))}
                  </div>

                  {analysis.integration_candidates.length > 0 && (
                    <div className="space-y-1.5">
                      <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider">
                        Ranked Integration Candidates
                      </span>
                      <ul data-testid="analysis-candidates" className="space-y-1">
                        {analysis.integration_candidates.map((candidate) => (
                          <li
                            key={candidate.path}
                            className="flex items-center justify-between gap-3 text-xs font-mono text-[var(--text-primary)]"
                          >
                            <span className="truncate">{candidate.path}</span>
                            <span className="flex items-center gap-2 shrink-0">
                              <span className="text-[var(--text-muted)]">
                                {Math.round(candidate.confidence * 100)}%
                              </span>
                              <button
                                type="button"
                                data-testid={`use-candidate-${candidate.path}`}
                                onClick={() => handleSelectTarget(candidate.path)}
                                disabled={isSelecting || config.widget_target_path === candidate.path}
                                className="px-2 py-0.5 rounded-md border border-[var(--border)] text-[10px] font-semibold text-[var(--color-purple)] hover:border-[var(--color-purple)]/40 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-default"
                              >
                                {config.widget_target_path === candidate.path ? 'Selected' : 'Use this'}
                              </button>
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {analysis.entry_points.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider">
                        Entry Points
                      </span>
                      <p className="text-xs font-mono text-[var(--text-secondary)] truncate">
                        {analysis.entry_points.join(', ')}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Next Recommended Step Banner */}
            <div className="p-5 rounded-2xl bg-purple-50/70 dark:bg-purple-950/20 border border-purple-200/70 dark:border-purple-900/40 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="text-xs font-bold text-purple-700 dark:text-purple-300 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Next Recommended Stage: Knowledge Base</span>
                </div>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  Your website is connected. Ground your assistant with verified facts, FAQs, and documentation.
                </p>
              </div>

              <button
                type="button"
                data-testid="advance-to-knowledge"
                onClick={() => setActiveItem('knowledge')}
                className="px-4 py-2.5 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white text-xs font-medium shadow-xs transition-all cursor-pointer flex items-center justify-center gap-1.5 shrink-0"
              >
                <span>Configure Knowledge</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Disconnect action */}
            <div className="pt-2 flex justify-end">
              <button
                type="button"
                data-testid="disconnect-website-button"
                onClick={disconnect}
                disabled={isDisconnecting}
                className="text-xs text-[var(--text-muted)] hover:text-rose-500 transition-colors cursor-pointer font-medium"
              >
                {isDisconnecting ? 'Disconnecting...' : 'Disconnect website'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STATE A: Not Connected — GitHub App connection */}
      {!isLoading && !isConnected && (
        <div
          data-testid="website-connection-form"
          className="rounded-3xl bg-[var(--surface)] border border-[var(--border)] shadow-xs p-6 sm:p-8 space-y-6"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)]/70 pb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-purple-50 text-purple-600 dark:bg-purple-950/60 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40 flex items-center justify-center shrink-0">
                <FolderGit2 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Connect GitHub</h3>
                <p className="text-xs text-[var(--text-muted)]">
                  {installations.length === 0
                    ? 'Install the Fussion GitHub App and choose which repositories it may access.'
                    : 'Select the repository Fussion should integrate.'}
                </p>
              </div>
            </div>
          </div>

          {installations.length === 0 ? (
            <div className="space-y-4">
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                Fussion never stores a password or a personal access token. The GitHub App grants
                access to the repositories you choose, and Fussion mints a short-lived token only
                when it needs one.
              </p>
              <button
                type="button"
                data-testid="connect-github-button"
                onClick={handleConnectGitHub}
                disabled={isConnectingGitHub}
                className="px-5 py-2.5 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white font-medium text-xs shadow-xs transition-all cursor-pointer flex items-center gap-2 group disabled:opacity-50"
              >
                {isConnectingGitHub ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <FolderGit2 className="w-3.5 h-3.5" />
                )}
                <span>{isConnectingGitHub ? 'Opening GitHub…' : 'Connect GitHub'}</span>
                <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <input
                type="text"
                data-testid="repo-search"
                value={repoQuery}
                onChange={(e) => setRepoQuery(e.target.value)}
                placeholder="Search repositories…"
                className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] focus:border-[var(--color-purple)] rounded-xl px-3.5 py-2.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none transition-colors font-mono"
              />

              {isLoadingRepositories ? (
                <div
                  data-testid="repositories-loading"
                  className="p-6 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)]/80 flex items-center justify-center gap-2 text-xs text-[var(--text-muted)] font-mono"
                >
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Loading repositories…</span>
                </div>
              ) : filteredRepositories.length === 0 ? (
                <p
                  data-testid="repositories-empty"
                  className="text-xs text-[var(--text-muted)] text-center py-6"
                >
                  No repositories match.
                </p>
              ) : (
                <ul className="space-y-2">
                  {filteredRepositories.map((repo) => (
                    <li
                      key={repo.full_name}
                      data-testid={`repo-card-${repo.full_name}`}
                      className="flex items-center justify-between gap-3 p-3.5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)]/80"
                    >
                      <div className="min-w-0 space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-semibold font-mono text-[var(--text-primary)] truncate">
                            {repo.full_name}
                          </span>
                          {repo.private && <Lock className="w-3 h-3 text-[var(--text-muted)]" />}
                        </div>
                        <div className="flex items-center gap-1.5 text-[10px] font-mono text-[var(--text-muted)]">
                          <GitBranch className="w-3 h-3" />
                          <span>{repo.default_branch}</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        data-testid={`select-repo-${repo.full_name}`}
                        onClick={() => handleSelectRepo(repo)}
                        disabled={isConnecting}
                        className="px-3 py-1.5 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white text-[11px] font-medium transition-all cursor-pointer disabled:opacity-50 shrink-0"
                      >
                        {isConnecting ? 'Connecting…' : 'Select'}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
