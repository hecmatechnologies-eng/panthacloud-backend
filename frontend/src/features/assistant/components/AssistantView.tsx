'use client';

import React from 'react';
import { AlertTriangle, Bot, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';
import { useAssistant } from '../hooks/useAssistant';
import { AssistantIdentityForm } from './AssistantIdentityForm';
import { AssistantAppearanceForm } from './AssistantAppearanceForm';
import { AssistantBehaviorForm } from './AssistantBehaviorForm';
import { AssistantPreview } from './AssistantPreview';
import { AssistantStatus } from './AssistantStatus';
import { AssistantSaveBar } from './AssistantSaveBar';

interface AssistantViewProps {
  orgId?: string;
  projectId?: string;
}

export const AssistantView: React.FC<AssistantViewProps> = ({ orgId, projectId }) => {
  const {
    config,
    previewPayload,
    draft,
    isLoading,
    isSaving,
    isResetting,
    isDirty,
    error,
    success,
    updateField,
    save,
    discard,
    reset,
    reload,
  } = useAssistant(orgId, projectId);

  if (!orgId || !projectId) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center space-y-3">
        <Bot className="w-10 h-10 text-zinc-600 mx-auto" />
        <h3 className="text-sm font-semibold text-zinc-300">No Project Selected</h3>
        <p className="text-xs text-zinc-500 max-w-sm mx-auto">
          Please select or create a project from the top navigation to configure its AI assistant.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-20 relative">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-violet-400" />
            <h1 className="text-lg font-bold text-white tracking-tight">
              Assistant Configuration &amp; Widget Studio
            </h1>
            <span className="text-[10px] font-mono uppercase bg-violet-950/80 border border-violet-800 text-violet-300 px-2 py-0.5 rounded font-semibold">
              Phase 10
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            Configure your storefront assistant&apos;s branding, greeting, and position with instantaneous live widget preview.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={reload}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-medium transition-colors disabled:opacity-50"
            title="Reload assistant configuration from server"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-violet-400' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="bg-rose-950/40 border border-rose-800/80 text-rose-300 px-4 py-3 rounded-xl text-xs flex items-center gap-2.5">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="bg-emerald-950/40 border border-emerald-800/80 text-emerald-300 px-4 py-3 rounded-xl text-xs flex items-center gap-2.5">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* Status Bar */}
      <AssistantStatus config={config} previewPayload={previewPayload} />

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Form Controls */}
        <div className="lg:col-span-6 space-y-5">
          <AssistantIdentityForm draft={draft} updateField={updateField} />
          <AssistantAppearanceForm draft={draft} updateField={updateField} />
          <AssistantBehaviorForm draft={draft} updateField={updateField} />
        </div>

        {/* Right Column: Sticky Live Widget Mockup */}
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
