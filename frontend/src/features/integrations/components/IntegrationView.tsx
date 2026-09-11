'use client';

import React from 'react';
import { GitPullRequest, AlertCircle, CheckCircle2, RefreshCw } from 'lucide-react';
import { useIntegration } from '../hooks/useIntegration';
import { RepositoryConnectionForm } from './RepositoryConnectionForm';
import { IntegrationStatus } from './IntegrationStatus';
import { IntegrationPlan } from './IntegrationPlan';
import { SandboxPreview } from './SandboxPreview';
import { IntegrationActions } from './IntegrationActions';
import { PullRequestCard } from './PullRequestCard';
import { IntegrationHistory } from './IntegrationHistory';

interface IntegrationViewProps {
  orgId?: string;
  projectId?: string;
}

export const IntegrationView: React.FC<IntegrationViewProps> = ({ orgId, projectId }) => {
  const {
    config,
    form,
    plan,
    validation,
    runs,
    latestRun,
    selectedRunDiff,
    selectedPR,
    isLoading,
    isSaving,
    isValidating,
    isPlanning,
    isExecuting,
    error,
    successMessage,
    updateFormField,
    saveConfiguration,
    validateConnection,
    generatePlan,
    executePipelineRun,
    viewDiff,
    cancelRun,
    deleteConfiguration,
    clearSelectedDiff,
    clearSuccess,
    clearError,
  } = useIntegration(orgId, projectId);

  if (!projectId) {
    return (
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-12 text-center space-y-3">
        <GitPullRequest className="w-8 h-8 text-zinc-600 mx-auto" />
        <h3 className="text-sm font-bold text-white">No Project Selected</h3>
        <p className="text-xs text-zinc-400 max-w-sm mx-auto">
          Please select or create a project to configure automated website integration and GitHub Pull Requests.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <GitPullRequest className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                <span>Automated Website Integration &amp; Pull Request Pipeline</span>
                <span className="text-[10px] font-mono uppercase bg-emerald-950/80 border border-emerald-800 text-emerald-300 px-2 py-0.5 rounded font-semibold">
                  Phase 11
                </span>
              </h1>
              <p className="text-xs text-zinc-400 mt-0.5">
                Generate deterministic widget code in an isolated sandbox and open a GitHub Pull Request for human review.
              </p>
            </div>
          </div>
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400" />
            <span>Loading configuration...</span>
          </div>
        )}
      </div>

      {/* Alerts */}
      {error && (
        <div className="flex items-center justify-between bg-rose-950/50 border border-rose-800/80 text-rose-300 px-4 py-3 rounded-xl text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={clearError}
            className="text-rose-400 hover:text-rose-200 text-xs font-semibold ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {successMessage && (
        <div className="flex items-center justify-between bg-emerald-950/50 border border-emerald-800/80 text-emerald-300 px-4 py-3 rounded-xl text-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
            <span>{successMessage}</span>
          </div>
          <button
            type="button"
            onClick={clearSuccess}
            className="text-emerald-400 hover:text-emerald-200 text-xs font-semibold ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Selected / Created PR Card */}
      {selectedPR && (
        <PullRequestCard pr={selectedPR} />
      )}

      {/* Top Row: Form & Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <RepositoryConnectionForm
            form={form}
            config={config}
            isSaving={isSaving}
            onFieldChange={updateFormField}
            onSave={saveConfiguration}
            onDelete={deleteConfiguration}
          />
        </div>
        <div className="lg:col-span-1">
          <IntegrationStatus config={config} latestRun={latestRun} />
        </div>
      </div>

      {/* Action Bar */}
      <IntegrationActions
        config={config}
        plan={plan}
        isValidating={isValidating}
        isPlanning={isPlanning}
        isExecuting={isExecuting}
        onValidate={validateConnection}
        onGeneratePlan={generatePlan}
        onExecute={executePipelineRun}
      />

      {/* Middle Row: Plan & Sandbox Security Preview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <IntegrationPlan
          plan={plan}
          onGeneratePlan={generatePlan}
          isPlanning={isPlanning}
        />
        <SandboxPreview validation={validation} />
      </div>

      {/* Bottom Section: History */}
      <IntegrationHistory
        runs={runs}
        selectedDiff={selectedRunDiff}
        onViewDiff={viewDiff}
        onCancelRun={cancelRun}
        onCloseDiff={clearSelectedDiff}
      />
    </div>
  );
};
