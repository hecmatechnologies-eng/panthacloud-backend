'use client';

import React from 'react';
import { useProject } from '../context';
import { STAGE_CONFIGS } from '../stageConfigs';
import { StageId } from '../types';
import { ArrowLeft, Clock } from 'lucide-react';

export interface StageDependencyViewProps {
  stageId: StageId;
  className?: string;
}

export const StageDependencyView: React.FC<StageDependencyViewProps> = ({
  stageId,
  className = '',
}) => {
  const { setActiveItem } = useProject();
  const config = STAGE_CONFIGS[stageId];
  const targetStage = config?.targetStage || 'website';
  const targetConfig = STAGE_CONFIGS[targetStage];

  if (!config) return null;

  return (
    <div
      data-testid="stage-dependency-view"
      className={`flex-1 w-full max-w-2xl py-4 space-y-6 text-left transition-all ${className}`}
    >
      {/* Back to Overview button */}
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

      {/* Main Guided Card */}
      <div className="rounded-3xl bg-[var(--surface)] border border-[var(--border)] shadow-xs p-6 sm:p-8 space-y-6">
        {/* Header Badges & Title */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold uppercase tracking-wider bg-purple-100/80 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40">
              {config.section}
              {config.stepNumber ? ` · Stage ${config.stepNumber} of 5` : ''}
            </span>
          </div>

          <h2
            data-testid="dependency-stage-title"
            className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--text-primary)] transition-colors"
          >
            {config.dependencyTitle || config.title}
          </h2>

          <p className="text-xs sm:text-sm text-[var(--text-secondary)] transition-colors leading-relaxed">
            {config.dependencyExplanation ||
              'This stage is pending completion of previous construction steps.'}
          </p>
        </div>

        {/* Current Status Box */}
        <div className="rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <div className="text-[11px] font-mono text-[var(--text-muted)] uppercase tracking-wider">
            Current status
          </div>
          <div
            data-testid="dependency-status-label"
            className="flex items-center gap-2 text-xs font-mono font-medium text-[var(--text-secondary)]"
          >
            <Clock className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
            <span>{config.dependencyStatusLabel || 'Waiting for prerequisite'}</span>
          </div>
        </div>

        {/* What to do first & Next Action */}
        <div className="rounded-2xl bg-[var(--surface-elevated)]/60 border border-[var(--border)]/80 p-5 space-y-3">
          <div className="text-[11px] font-mono font-medium text-[var(--text-muted)] uppercase tracking-wider">
            What to do first
          </div>

          <p className="text-xs sm:text-sm text-[var(--text-secondary)] leading-relaxed">
            {config.whatToDoFirst ||
              `Complete the ${targetConfig?.title || 'previous'} stage to unlock this step.`}
          </p>

          <div className="pt-2">
            <button
              type="button"
              data-testid="dependency-cta-button"
              onClick={() => setActiveItem(targetStage)}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white font-medium text-xs shadow-xs transition-all cursor-pointer group"
            >
              <span>{config.actionLabel || `Go to ${targetConfig?.title || 'Prerequisite'} →`}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
