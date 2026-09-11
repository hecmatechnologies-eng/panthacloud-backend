'use client';

import React from 'react';
import { AlertCircle, Check, Loader2, RotateCcw, X } from 'lucide-react';

interface AssistantSaveBarProps {
  isDirty: boolean;
  isSaving: boolean;
  isResetting: boolean;
  onSave: () => Promise<void>;
  onDiscard: () => void;
  onReset: () => Promise<void>;
}

export const AssistantSaveBar: React.FC<AssistantSaveBarProps> = ({
  isDirty,
  isSaving,
  isResetting,
  onSave,
  onDiscard,
  onReset,
}) => {
  if (!isDirty && !isSaving && !isResetting) {
    return null;
  }

  const handleReset = async () => {
    if (
      window.confirm(
        'Are you sure you want to reset this assistant to canonical Fussion defaults? Custom branding and greetings will be restored to their initial baseline.'
      )
    ) {
      await onReset();
    }
  };

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 w-full max-w-2xl px-4 animate-in fade-in slide-in-from-bottom-4 duration-200">
      <div className="bg-[var(--surface-elevated)]/95 backdrop-blur-md border border-[var(--color-purple)]/40 shadow-2xl rounded-2xl p-3 sm:px-5 sm:py-3 flex items-center justify-between gap-4 text-[var(--text-primary)] ring-1 ring-[var(--color-purple)]/20">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-xs font-semibold text-[var(--text-primary)] flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
            Unsaved Changes
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={isSaving || isResetting}
            onClick={handleReset}
            className="px-2.5 py-1.5 text-xs text-[var(--text-muted)] hover:text-rose-400 transition-colors flex items-center gap-1 font-medium disabled:opacity-50 cursor-pointer"
            title="Reset assistant configuration to original defaults"
          >
            <RotateCcw className="w-3 h-3" />
            <span className="hidden sm:inline">Reset Defaults</span>
          </button>

          <button
            type="button"
            disabled={isSaving || isResetting}
            onClick={onDiscard}
            className="px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--surface)] hover:bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl transition-colors flex items-center gap-1 font-medium disabled:opacity-50 cursor-pointer"
          >
            <X className="w-3 h-3" />
            <span>Discard</span>
          </button>

          <button
            type="button"
            disabled={isSaving || isResetting}
            onClick={onSave}
            className="px-4 py-1.5 text-xs font-medium text-white bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 rounded-xl shadow-xs transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                <span>Save Changes</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
