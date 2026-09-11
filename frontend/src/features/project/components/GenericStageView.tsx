'use client';

import React from 'react';
import { useProject } from '../context';
import { STAGE_CONFIGS } from '../stageConfigs';
import { StageId } from '../types';
import { ArrowLeft, CheckCircle2, ArrowRight } from 'lucide-react';

export interface GenericStageViewProps {
  stageId: StageId;
  className?: string;
}

export const GenericStageView: React.FC<GenericStageViewProps> = ({
  stageId,
  className = '',
}) => {
  const { setActiveItem, isStageCompleted, markStageCompleted } = useProject();
  const config = STAGE_CONFIGS[stageId];
  const isCompleted = isStageCompleted(stageId);

  if (!config) return null;

  return (
    <div
      data-testid={`stage-view-${stageId}`}
      className={`flex-1 w-full max-w-3xl py-4 space-y-6 text-left transition-all ${className}`}
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

      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold uppercase tracking-wider bg-purple-100/80 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40">
            {config.section}
            {config.stepNumber ? ` · Stage ${config.stepNumber} of 5` : ''}
          </span>
          {isCompleted && (
            <span className="flex items-center gap-1 text-[11px] font-mono text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Configured</span>
            </span>
          )}
        </div>

        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--text-primary)] transition-colors">
          {config.title}
        </h2>
      </div>

      {/* Surface Card */}
      <div className="rounded-3xl bg-[var(--surface)] border border-[var(--border)] shadow-xs p-6 sm:p-8 space-y-6">
        <p className="text-xs sm:text-sm text-[var(--text-secondary)] leading-relaxed">
          {stageId === 'knowledge' &&
            'Ground your assistant with verified facts, uploaded documentation, FAQs, and web crawl sources.'}
          {stageId === 'assistant' &&
            'Customize your assistant persona, system instructions, tone, and chat widget appearance.'}
          {stageId === 'integration' &&
            'Run sandbox integration, inspect framework components, and review automated pull requests.'}
          {stageId === 'preview' &&
            'Interact with your assistant in a live preview sandbox before activating production runtime.'}
          {stageId === 'settings' &&
            'Manage project preferences, API credentials, and administrative controls.'}
        </p>

        {stageId !== 'settings' && (
          <div className="pt-4 border-t border-[var(--border)]/70 flex items-center justify-between">
            <span className="text-xs text-[var(--text-muted)] font-mono">
              Stage status: {isCompleted ? 'Completed' : 'Active'}
            </span>

            <button
              type="button"
              data-testid={`mark-complete-${stageId}`}
              onClick={() => markStageCompleted(stageId, !isCompleted)}
              className="px-4 py-2 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white text-xs font-medium transition-all cursor-pointer flex items-center gap-1.5"
            >
              <span>{isCompleted ? 'Mark as Incomplete' : 'Complete Stage'}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
