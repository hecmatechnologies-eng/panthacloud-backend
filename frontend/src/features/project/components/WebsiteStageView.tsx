'use client';

import React, { useState } from 'react';
import { useProject } from '../context';
import { useWebsiteStage } from '../hooks/useWebsiteStage';
import { Project } from '@/lib/api';
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
    isLoading,
    isConnecting,
    isDisconnecting,
    isAnalyzing,
    error,
    connect,
    disconnect,
    analyze,
    clearError,
  } = useWebsiteStage({
    orgId,
    projectId: project.id,
    onStatusChange: handleStatusChange,
  });

  // Form local state
  const [owner, setOwner] = useState('');
  const [repo, setRepo] = useState('');
  const [branch, setBranch] = useState('main');
  const [token, setToken] = useState('');

  const handleFillDemo = () => {
    setOwner('acme-corp');
    setRepo('storefront-web');
    setBranch('main');
    setToken('');
    clearError();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!owner.trim() || !repo.trim()) return;

    try {
      await connect({
        repository_owner: owner.trim(),
        repository_name: repo.trim(),
        default_branch: branch.trim() || 'main',
        website_root_dir: '/',
        github_token: token.trim() || undefined,
      });
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

  const isConnected = config?.status === 'CONNECTED';
  const topCandidate = analysis?.integration_candidates?.[0];

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
                            <span className="text-[var(--text-muted)] shrink-0">
                              {Math.round(candidate.confidence * 100)}%
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

      {/* STATE A: Not Connected / Connection Form */}
      {!isLoading && !isConnected && (
        <form
          data-testid="website-connection-form"
          onSubmit={handleSubmit}
          className="rounded-3xl bg-[var(--surface)] border border-[var(--border)] shadow-xs p-6 sm:p-8 space-y-6"
        >
          {/* Form Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)]/70 pb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-purple-50 text-purple-600 dark:bg-purple-950/60 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40 flex items-center justify-center shrink-0">
                <FolderGit2 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">
                  Connect GitHub Repository
                </h3>
                <p className="text-xs text-[var(--text-muted)]">
                  Specify your public or private website repository.
                </p>
              </div>
            </div>

            <button
              type="button"
              data-testid="fill-demo-preset"
              onClick={handleFillDemo}
              className="px-3 py-1 rounded-full bg-[var(--surface-elevated)] hover:bg-[var(--surface)] border border-[var(--border)] text-[11px] font-mono text-[var(--color-purple)] hover:border-[var(--color-purple)]/40 transition-colors cursor-pointer self-start sm:self-center"
            >
              Fill Sample Demo
            </button>
          </div>

          {/* Form Inputs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Repository Owner */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-[var(--text-secondary)]">
                GitHub Owner / Organization
              </label>
              <input
                type="text"
                required
                data-testid="repo-owner-input"
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
                placeholder="e.g. acme-corp"
                className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] focus:border-[var(--color-purple)] rounded-xl px-3.5 py-2.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none transition-colors font-mono"
              />
            </div>

            {/* Repository Name */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-[var(--text-secondary)]">
                Repository Name
              </label>
              <input
                type="text"
                required
                data-testid="repo-name-input"
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                placeholder="e.g. storefront-web"
                className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] focus:border-[var(--color-purple)] rounded-xl px-3.5 py-2.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none transition-colors font-mono"
              />
            </div>

            {/* Default Branch */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-[var(--text-secondary)]">
                Default Branch
              </label>
              <input
                type="text"
                required
                data-testid="repo-branch-input"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main"
                className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] focus:border-[var(--color-purple)] rounded-xl px-3.5 py-2.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none transition-colors font-mono"
              />
            </div>

            {/* GitHub Access Token */}
            <div className="space-y-1.5 sm:col-span-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-[var(--text-secondary)]">
                  GitHub Personal Access Token (Optional for public repositories)
                </label>
                <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" />
                  <span>Encrypted via Vault</span>
                </span>
              </div>
              <input
                type="password"
                data-testid="github-token-input"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="ghp_****************************************"
                className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] focus:border-[var(--color-purple)] rounded-xl px-3.5 py-2.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none transition-colors font-mono"
              />
              <p className="text-[11px] text-[var(--text-muted)] leading-relaxed">
                The framework, app shell and integration point are detected from the repository by
                the analyst. No framework selection or target path is required.
              </p>
            </div>
          </div>

          {/* Submit Action */}
          <div className="pt-3 border-t border-[var(--border)]/70 flex justify-end">
            <button
              type="submit"
              data-testid="connect-website-submit"
              disabled={isConnecting}
              className="px-5 py-2.5 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white font-medium text-xs shadow-xs transition-all cursor-pointer flex items-center gap-2 group disabled:opacity-50"
            >
              {isConnecting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Connecting repository...</span>
                </>
              ) : (
                <>
                  <span>Connect Website</span>
                  <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>
          </div>
        </form>
      )}
    </div>
  );
};
