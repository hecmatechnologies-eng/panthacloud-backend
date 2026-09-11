'use client';

import React from 'react';
import { Check, CircleDashed, Clock3, LoaderCircle, X } from 'lucide-react';
import { useProject } from '../context';
import { STAGE_CONFIGS } from '../stageConfigs';
import { StudioRunStatus } from '../types';

const statusStyles: Record<StudioRunStatus, { label: string; icon: React.FC<{ className?: string }>; className: string }> = {
  idle: { label: 'Ready', icon: CircleDashed, className: 'text-[var(--text-muted)]' },
  running: { label: 'Working', icon: LoaderCircle, className: 'text-purple-600 dark:text-purple-300' },
  success: { label: 'Done', icon: Check, className: 'text-emerald-600 dark:text-emerald-400' },
  failed: { label: 'Needs attention', icon: X, className: 'text-red-600 dark:text-red-400' },
  waiting: { label: 'Waiting', icon: Clock3, className: 'text-[var(--text-muted)]' },
};

const formatTime = (value: string) => new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(value));

export const StudioStageWorkspace: React.FC = () => {
  const { pinnedStageIds, studioActivity, setActiveItem, unpinStage, getStageRunStatus } = useProject();

  if (pinnedStageIds.length === 0 && studioActivity.length === 0) return null;

  return (
    <aside data-testid="stage-workspace" className="w-full xl:w-72 shrink-0 space-y-3">
      <div className="flex items-center justify-between px-1">
        <span className="text-[10px] font-mono font-medium tracking-wider text-[var(--text-muted)]">WORKSPACE</span>
        <span className="text-[10px] font-mono text-[var(--text-muted)]">{pinnedStageIds.length} pinned</span>
      </div>

      {pinnedStageIds.map((stageId) => {
        const stage = STAGE_CONFIGS[stageId];
        const state = statusStyles[getStageRunStatus(stageId)];
        const Icon = state.icon;
        return (
          <section key={stageId} data-testid={`pinned-stage-${stageId}`} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3 shadow-xs">
            <div className="flex items-start gap-2">
              <button type="button" onClick={() => setActiveItem(stageId)} className="min-w-0 flex-1 text-left cursor-pointer">
                <div className="text-xs font-semibold text-[var(--text-primary)]">{stage.title}</div>
                <div className={`mt-1 flex items-center gap-1 text-[10px] font-mono ${state.className}`}>
                  <Icon className={`h-3 w-3 ${getStageRunStatus(stageId) === 'running' ? 'animate-spin' : ''}`} />
                  {state.label}
                </div>
              </button>
              <button type="button" aria-label={`Remove ${stage.title} from workspace`} onClick={() => unpinStage(stageId)} className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </section>
        );
      })}

      {studioActivity.length > 0 && (
        <section data-testid="studio-activity-feed" className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3 shadow-xs">
          <div className="mb-2 text-[10px] font-mono font-medium tracking-wider text-[var(--text-muted)]">SYSTEM ACTIVITY</div>
          <div className="space-y-2">
            {studioActivity.slice(0, 4).map((event) => {
              const state = statusStyles[event.status];
              const Icon = state.icon;
              return <div key={event.id} className="flex gap-2 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                <Icon className={`mt-0.5 h-3 w-3 shrink-0 ${state.className}`} />
                <div><span>{event.message}</span><span className="ml-1 font-mono text-[10px] text-[var(--text-muted)]">{formatTime(event.createdAt)}</span></div>
              </div>;
            })}
          </div>
        </section>
      )}
    </aside>
  );
};
