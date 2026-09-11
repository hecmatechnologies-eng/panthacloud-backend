'use client';

import React from 'react';
import { Project } from '@/lib/api';
import { useProject } from '../context';
import { StageId } from '../types';
import {
  Globe,
  BookOpen,
  Bot,
  Plug,
  Play,
  CheckCircle2,
  ExternalLink,
  Check,
} from 'lucide-react';

export interface ProjectStudioViewProps {
  project: Project;
  className?: string;
}

interface LifecycleCardConfig {
  id: StageId;
  stageNumber: number;
  phase: '1. BUILD' | '2. BUILD' | '3. BUILD' | '4. CONNECT' | '5. LIVE';
  title: string;
  description: string;
  icon: React.FC<{ className?: string }>;
  actionLabel: string;
  waitingStatus: string;
  waitingAction: string;
}

const lifecycleCards: LifecycleCardConfig[] = [
  {
    id: 'website',
    stageNumber: 1,
    phase: '1. BUILD',
    title: 'Website Connection',
    description: 'Connect your public website repository or domain.',
    icon: Globe,
    actionLabel: 'Connect website →',
    waitingStatus: 'Not connected',
    waitingAction: 'Connect website →',
  },
  {
    id: 'knowledge',
    stageNumber: 2,
    phase: '2. BUILD',
    title: 'Knowledge Base',
    description: 'Ground your assistant with verified company facts and documentation.',
    icon: BookOpen,
    actionLabel: 'Configure knowledge →',
    waitingStatus: 'Waiting for website',
    waitingAction: 'Website connection required →',
  },
  {
    id: 'assistant',
    stageNumber: 3,
    phase: '3. BUILD',
    title: 'Assistant Configuration',
    description: 'Design identity, persona, behavior, and widget appearance.',
    icon: Bot,
    actionLabel: 'Configure assistant →',
    waitingStatus: 'Waiting for knowledge',
    waitingAction: 'Knowledge required →',
  },
  {
    id: 'integration',
    stageNumber: 4,
    phase: '4. CONNECT',
    title: 'Sandbox Integration',
    description: 'Prepare deterministic code artifacts and review pull request.',
    icon: Plug,
    actionLabel: 'Start integration →',
    waitingStatus: 'Waiting for assistant',
    waitingAction: 'Assistant required →',
  },
  {
    id: 'preview',
    stageNumber: 5,
    phase: '5. LIVE',
    title: 'Live Visitor Runtime',
    description: 'Activate streaming responses for real visitors on your production site.',
    icon: Play,
    actionLabel: 'Go live →',
    waitingStatus: 'Waiting for integration',
    waitingAction: 'Integration required →',
  },
];

const stepperStages: { id: StageId; step: number; label: string; defaultSubtitle: string }[] = [
  { id: 'website', step: 1, label: 'Website', defaultSubtitle: 'Connect your site' },
  { id: 'knowledge', step: 2, label: 'Knowledge', defaultSubtitle: 'Add your content' },
  { id: 'assistant', step: 3, label: 'Assistant', defaultSubtitle: 'Configure behaviour' },
  { id: 'integration', step: 4, label: 'Integration', defaultSubtitle: 'Install and connect' },
  { id: 'preview', step: 5, label: 'Live', defaultSubtitle: 'Go live' },
];

export const ProjectStudioView: React.FC<ProjectStudioViewProps> = ({
  project,
  className = '',
}) => {
  const { setActiveItem, isStageCompleted, isStageActionable } = useProject();

  // Determine which stage is currently the active recommended next step
  const activeRecommendedStage =
    stepperStages.find(
      (s) => isStageActionable(s.id) && !isStageCompleted(s.id)
    )?.id || 'website';

  return (
    <div
      data-testid="project-studio-view"
      className={`flex-1 w-full max-w-4xl space-y-6 sm:space-y-7 py-2 text-left ${className}`}
    >
      {/* Project Overview Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold uppercase tracking-wider bg-purple-100/80 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40">
            Project Studio
          </span>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h1
            data-testid="project-title"
            className="text-2xl sm:text-3xl font-extrabold tracking-tight text-[var(--text-primary)] transition-colors"
          >
            {project.name}
          </h1>

          <div className="inline-flex items-center px-3 py-1 rounded-full border border-[var(--border)] bg-[var(--surface)] text-[11px] font-mono text-[var(--text-muted)] shadow-xs select-none">
            BUILD → CONNECT → LIVE
          </div>
        </div>

        <p className="text-xs sm:text-sm text-[var(--text-secondary)] transition-colors max-w-2xl leading-relaxed">
          {project.description ||
            'Build your AI assistant. Your project is getting started. Configure each stage below to build, connect, and go live.'}
        </p>
      </div>

      {/* Dynamic 5-Step Progress Stepper Card */}
      <div
        data-testid="stepper-card"
        className="rounded-2xl bg-[var(--surface)] border border-[var(--border)] p-4 shadow-xs flex items-center justify-between overflow-x-auto gap-2"
      >
        {stepperStages.map((item, index) => {
          const isCompleted = isStageCompleted(item.id);
          const isCurrentActionable = item.id === activeRecommendedStage;

          return (
            <React.Fragment key={item.id}>
              <button
                type="button"
                data-testid={`stepper-step-${item.id}`}
                onClick={() => setActiveItem(item.id)}
                className="flex items-center gap-2.5 p-1.5 rounded-xl hover:bg-[var(--surface-elevated)] transition-all cursor-pointer text-left shrink-0 group"
              >
                {/* Number Circle / Checkmark */}
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-all ${
                    isCompleted
                      ? 'bg-emerald-500 text-white shadow-xs'
                      : isCurrentActionable
                      ? 'bg-[var(--color-purple)] text-white shadow-xs shadow-purple-950/20'
                      : 'bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--text-muted)] group-hover:border-[var(--text-muted)]'
                  }`}
                >
                  {isCompleted ? <Check className="w-3.5 h-3.5 stroke-[2.5]" /> : item.step}
                </div>

                {/* Text labels */}
                <div className="min-w-0">
                  <div
                    className={`text-xs font-semibold leading-tight ${
                      isCurrentActionable
                        ? 'text-[var(--text-primary)]'
                        : isCompleted
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]'
                    }`}
                  >
                    {item.label}
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)] truncate">
                    {isCompleted ? 'Completed' : item.defaultSubtitle}
                  </div>
                </div>
              </button>

              {index < stepperStages.length - 1 && (
                <div className="text-[var(--border)] text-sm px-1 shrink-0 select-none font-mono">
                  →
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Section Bar */}
      <div className="flex items-center justify-between text-xs font-mono text-[var(--text-muted)] pt-1">
        <span className="tracking-wider font-medium">CONSTRUCTION LIFECYCLE</span>
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[var(--color-purple)] hover:underline font-medium"
        >
          <span>View documentation</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>

      {/* 5 Status-Aware Lifecycle Cards (3 in row 1, 2 in row 2) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        {lifecycleCards.map((card) => {
          const Icon = card.icon;
          const isCompleted = isStageCompleted(card.id);
          const isActionable = isStageActionable(card.id);
          const isRecommended = card.id === activeRecommendedStage;

          // Status copy
          let statusText = card.waitingStatus;
          if (isCompleted) {
            statusText = 'Completed';
          } else if (card.id === 'website') {
            statusText = 'Not connected';
          } else if (isActionable) {
            statusText = 'Ready to configure';
          }

          const cardTestId =
            card.id === 'preview' ? 'lifecycle-card-live' : `lifecycle-card-${card.id}`;
          const actionTestId =
            card.id === 'preview' ? 'card-action-live' : `card-action-${card.id}`;

          return (
            <div
              key={card.id}
              data-testid={cardTestId}
              className={`rounded-2xl border p-5 flex flex-col justify-between space-y-4 shadow-xs transition-all text-left ${
                isRecommended
                  ? 'bg-purple-50/25 dark:bg-purple-950/15 border-purple-300 dark:border-purple-900/60 ring-1 ring-purple-500/20'
                  : 'bg-[var(--surface)] border-[var(--border)] hover:border-[var(--border)]/80'
              }`}
            >
              <div className="space-y-3">
                {/* Top Row: Icon container & Phase Badge */}
                <div className="flex items-center justify-between">
                  <div
                    className={`w-9 h-9 rounded-xl flex items-center justify-center transition-colors ${
                      isRecommended
                        ? 'bg-purple-100/80 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40'
                        : isCompleted
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                        : 'bg-[var(--surface-elevated)] text-[var(--text-secondary)] border border-[var(--border)]'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </div>

                  <span
                    className={`text-[11px] font-mono font-semibold tracking-wider ${
                      isRecommended
                        ? 'text-purple-600 dark:text-purple-400'
                        : 'text-[var(--text-muted)]'
                    }`}
                  >
                    {card.phase}
                  </span>
                </div>

                {/* Title & Description */}
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-[var(--text-primary)] transition-colors">
                    {card.title}
                  </h3>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed mt-1">
                    {card.description}
                  </p>
                </div>

                {/* Status Indicator */}
                <div className="flex items-center gap-1.5 text-[11px] font-mono text-[var(--text-muted)] pt-1">
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      isCompleted
                        ? 'bg-emerald-500'
                        : isRecommended
                        ? 'bg-purple-500'
                        : 'bg-[var(--border)]'
                    }`}
                  />
                  <span>{statusText}</span>
                </div>
              </div>

              {/* Action Button: Status-aware & ALWAYS Clickable */}
              <div>
                {isRecommended ? (
                  <button
                    type="button"
                    data-testid={actionTestId}
                    onClick={() => setActiveItem(card.id)}
                    className="w-full py-2.5 px-4 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white font-medium text-xs shadow-xs transition-all cursor-pointer flex items-center justify-center gap-2 group"
                  >
                    <span>{card.actionLabel}</span>
                  </button>
                ) : isCompleted ? (
                  <button
                    type="button"
                    data-testid={actionTestId}
                    onClick={() => setActiveItem(card.id)}
                    className="w-full py-2.5 px-4 rounded-xl bg-[var(--surface-elevated)] hover:bg-[var(--surface)] border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 font-medium text-xs transition-colors cursor-pointer flex items-center justify-center gap-2"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>View details</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    data-testid={actionTestId}
                    onClick={() => setActiveItem(card.id)}
                    className="w-full py-2.5 px-4 rounded-xl bg-[var(--surface-elevated)] hover:bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] font-medium text-xs transition-colors cursor-pointer flex items-center justify-center gap-1.5 group"
                  >
                    <span>{card.waitingAction}</span>
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
