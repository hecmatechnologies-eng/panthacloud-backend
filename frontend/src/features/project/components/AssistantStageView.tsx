'use client';

import React from 'react';
import { useProject } from '../context';
import { Project } from '@/lib/api';
import {
  useAssistant,
  AssistantIdentityForm,
  AssistantAppearanceForm,
  AssistantBehaviorForm,
  AssistantPreview,
  AssistantStatus,
  AssistantSaveBar,
  AssistantReadinessState,
} from '@/features/assistant';
import { StageDependencyView } from './StageDependencyView';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Bot,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';

export interface AssistantStageViewProps {
  project: Project;
  className?: string;
}

export const AssistantStageView: React.FC<AssistantStageViewProps> = ({
  project,
  className = '',
}) => {
  const { activeOrg, setActiveItem, markStageCompleted, isStageCompleted } = useProject();
  const orgId = project.organization_id || activeOrg?.id;

  const isKnowledgeDone = isStageCompleted('knowledge');

  const handleStatusChange = React.useCallback(
    (isReady: boolean, _readiness: AssistantReadinessState) => {
      if (isStageCompleted('assistant') !== isReady) {
        markStageCompleted('assistant', isReady);
      }
    },
    [isStageCompleted, markStageCompleted]
  );

  const {
    config,
    previewPayload,
    draft,
    isLoading: _isLoading,
    isSaving,
    isResetting,
    isDirty,
    error,
    success,
    readinessState,
    updateField,
    save,
    discard,
    reset,
  } = useAssistant(orgId, project.id, {
    onStatusChange: handleStatusChange,
    isKnowledgeGrounded: isKnowledgeDone,
  });

  // Prerequisite gate: If Knowledge is not completed, display dependency view
  if (!isKnowledgeDone) {
    return <StageDependencyView stageId="assistant" className={className} />;
  }

  return (
    <div
      data-testid="assistant-stage-view"
      className={`flex-1 w-full max-w-5xl py-4 space-y-6 text-left transition-colors duration-150 pb-24 ${className}`}
    >
      {/* Hidden marker for test compatibility */}
      <div data-testid="stage-view-assistant" className="hidden" aria-hidden="true" />

      {/* Back to Overview */}
      <div className="flex items-center justify-between">
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
            BUILD · Stage 3 of 5
          </span>
          {readinessState === 'ready_for_integration' && (
            <span
              data-testid="assistant-ready-badge"
              className="flex items-center gap-1 text-[11px] font-mono text-emerald-600 dark:text-emerald-400 font-medium"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Ready for Integration</span>
            </span>
          )}
        </div>

        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--text-primary)] transition-colors">
          Assistant Voice &amp; Widget Studio
        </h2>

        <p className="text-xs sm:text-sm text-[var(--text-secondary)] transition-colors leading-relaxed max-w-2xl">
          Design your storefront assistant&apos;s identity, customize its presentation, and establish behavioral guardrails with real-time interactive preview simulation.
        </p>
      </div>

      {/* Readiness & Handoff Banner: Appears when System Assertion is Satisfied */}
      {readinessState === 'ready_for_integration' && (
        <div
          data-testid="assistant-handoff-banner"
          className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shadow-xs"
        >
          <div className="flex items-center gap-2.5">
            <Sparkles className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <div>
              <span className="font-semibold text-emerald-950 dark:text-emerald-200 block">
                Your assistant is configured and grounded
              </span>
              <span className="text-emerald-800/80 dark:text-emerald-400/80 text-[11px]">
                Blueprint verified. Ready to compile website integration artifacts and open a Pull Request.
              </span>
            </div>
          </div>
          <button
            type="button"
            data-testid="start-integration-cta"
            onClick={() => setActiveItem('integration')}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs shadow-xs transition-colors shrink-0 cursor-pointer"
          >
            <span>Start Integration</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Notifications */}
      {error && (
        <div className="bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 px-4 py-3 rounded-2xl text-xs flex items-center gap-2.5 shadow-xs">
          <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 px-4 py-3 rounded-2xl text-xs flex items-center gap-2.5 shadow-xs">
          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* Metrics Strip */}
      <AssistantStatus
        config={config}
        previewPayload={previewPayload}
        readinessState={readinessState}
      />

      {/* 2-Column Responsive Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: 3 Configuration Pillars */}
        <div className="lg:col-span-6 space-y-5">
          <AssistantIdentityForm draft={draft} updateField={updateField} />
          <AssistantAppearanceForm draft={draft} updateField={updateField} />
          <AssistantBehaviorForm draft={draft} updateField={updateField} />
        </div>

        {/* Right Column: Sticky Live Widget Mockup Simulator */}
        <div className="lg:col-span-6 lg:sticky lg:top-6">
          <AssistantPreview draft={draft} previewPayload={previewPayload} />
        </div>
      </div>

      {/* Unsaved Changes Save Bar */}
      <AssistantSaveBar
        isDirty={isDirty}
        isSaving={isSaving}
        isResetting={isResetting}
        onSave={save}
        onDiscard={discard}
        onReset={reset}
      />
    </div>
  );
};
