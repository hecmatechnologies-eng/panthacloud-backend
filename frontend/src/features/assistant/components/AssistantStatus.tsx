'use client';

import React from 'react';
import { Bot, CheckCircle2, Database, Layout, Power } from 'lucide-react';
import { AssistantConfig, AssistantPreviewPayload } from '@/lib/api/assistant';
import { AssistantReadinessState } from '../types';

interface AssistantStatusProps {
  config: AssistantConfig | null;
  previewPayload: AssistantPreviewPayload | null;
  readinessState?: AssistantReadinessState;
}

export const AssistantStatus: React.FC<AssistantStatusProps> = ({
  config,
  previewPayload,
  readinessState,
}) => {
  const hasKnowledgeBase = previewPayload?.knowledge_base?.has_knowledge_base ?? false;
  const docsCount = previewPayload?.knowledge_base?.documents_count ?? 0;

  return (
    <div
      data-testid="assistant-metrics-strip"
      className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-3.5 shadow-xs"
    >
      {/* Assistant Status */}
      <div className="flex items-center gap-2.5">
        <div
          className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
            config?.is_enabled
              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
              : 'bg-[var(--surface-elevated)] text-[var(--text-muted)] border border-[var(--border)]'
          }`}
        >
          <Power className="w-3.5 h-3.5" />
        </div>
        <div>
          <span className="text-[10px] uppercase font-mono text-[var(--text-muted)] block">
            Widget Status
          </span>
          <span
            className={`text-xs font-semibold ${
              config?.is_enabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-[var(--text-muted)]'
            }`}
          >
            {config?.is_enabled ? 'Active' : 'Disabled'}
          </span>
        </div>
      </div>

      {/* Screen Position */}
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-lg bg-[var(--surface-elevated)] border border-[var(--border)] flex items-center justify-center shrink-0 text-[var(--color-purple)]">
          <Layout className="w-3.5 h-3.5" />
        </div>
        <div>
          <span className="text-[10px] uppercase font-mono text-[var(--text-muted)] block">
            Position
          </span>
          <span className="text-xs font-medium text-[var(--text-primary)]">
            {config?.position === 'BOTTOM_LEFT' ? 'Bottom Left' : 'Bottom Right'}
          </span>
        </div>
      </div>

      {/* Knowledge Base Grounding */}
      <div className="flex items-center gap-2.5">
        <div
          className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
            hasKnowledgeBase
              ? 'bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 border border-purple-200 dark:border-purple-900/40'
              : 'bg-[var(--surface-elevated)] text-[var(--text-muted)] border border-[var(--border)]'
          }`}
        >
          <Database className="w-3.5 h-3.5" />
        </div>
        <div>
          <span className="text-[10px] uppercase font-mono text-[var(--text-muted)] block">
            Knowledge Grounding
          </span>
          <span className="text-xs font-medium text-[var(--text-primary)]">
            {hasKnowledgeBase ? `${docsCount} Document(s)` : 'No Docs Ingested'}
          </span>
        </div>
      </div>

      {/* Readiness Assertion */}
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-lg bg-[var(--surface-elevated)] border border-[var(--border)] flex items-center justify-center shrink-0 text-[var(--color-purple)]">
          <CheckCircle2 className="w-3.5 h-3.5" />
        </div>
        <div>
          <span className="text-[10px] uppercase font-mono text-[var(--text-muted)] block">
            Readiness State
          </span>
          <span className="text-xs font-mono font-medium text-[var(--text-primary)] capitalize">
            {readinessState === 'ready_for_integration'
              ? 'Ready for Integration'
              : readinessState === 'configured'
              ? 'Configured (Needs Grounding)'
              : readinessState === 'draft'
              ? 'Draft (Unsaved)'
              : config?.id
              ? 'Configured'
              : 'Uninitialized'}
          </span>
        </div>
      </div>
    </div>
  );
};
