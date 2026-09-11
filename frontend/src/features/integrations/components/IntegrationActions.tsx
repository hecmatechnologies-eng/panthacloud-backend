'use client';

import React from 'react';
import { CheckCircle, FileText, GitPullRequest, Loader2 } from 'lucide-react';
import { WebsiteIntegrationConfig, IntegrationPlanPayload } from '@/lib/api/integration';

interface IntegrationActionsProps {
  config: WebsiteIntegrationConfig | null;
  plan: IntegrationPlanPayload | null;
  isValidating: boolean;
  isPlanning: boolean;
  isExecuting: boolean;
  canExecute?: boolean;
  onValidate: () => void;
  onGeneratePlan: () => void;
  onExecute: () => void;
}

export const IntegrationActions: React.FC<IntegrationActionsProps> = ({
  config,
  plan,
  isValidating,
  isPlanning,
  isExecuting,
  canExecute = true,
  onValidate,
  onGeneratePlan,
  onExecute,
}) => {
  const isConfigured = !!config && !!config.repository_owner && !!config.repository_name;
  const canCreatePR = isConfigured && !isExecuting && canExecute;

  return (
    <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-5 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-lg backdrop-blur-md">
      <div className="space-y-0.5 text-left">
        <h4 className="text-xs font-bold text-white uppercase tracking-wider">
          Integration Pipeline Controls
        </h4>
        <p className="text-[11px] text-zinc-400">
          Validate configuration, inspect planned file changes, and open a dedicated GitHub Pull Request.
        </p>
      </div>

      <div className="flex items-center gap-2.5 flex-wrap sm:flex-nowrap">
        {/* Validate Connection */}
        <button
          type="button"
          onClick={onValidate}
          disabled={!isConfigured || isValidating || isExecuting}
          className="px-3.5 py-2 rounded-xl text-xs font-semibold text-zinc-300 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
        >
          {isValidating ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <CheckCircle className="w-3.5 h-3.5 text-zinc-400" />
          )}
          <span>{isValidating ? 'Checking...' : 'Validate Connection'}</span>
        </button>

        {/* Generate Plan */}
        <button
          type="button"
          onClick={onGeneratePlan}
          disabled={!isConfigured || isPlanning || isExecuting}
          className="px-3.5 py-2 rounded-xl text-xs font-semibold text-zinc-300 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
        >
          {isPlanning ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <FileText className="w-3.5 h-3.5 text-zinc-400" />
          )}
          <span>{isPlanning ? 'Planning...' : 'Generate Plan'}</span>
        </button>

        {/* Create Pull Request */}
        <button
          type="button"
          onClick={onExecute}
          disabled={!canCreatePR}
          className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-sm"
        >
          {isExecuting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <GitPullRequest className="w-4 h-4" />
          )}
          <span>{isExecuting ? 'Running Pipeline...' : 'Create Pull Request'}</span>
        </button>
      </div>
    </div>
  );
};
