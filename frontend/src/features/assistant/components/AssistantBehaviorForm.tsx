'use client';

import React from 'react';
import { Sliders, ShieldCheck, Power } from 'lucide-react';
import { AssistantFormState } from '../types';

interface AssistantBehaviorFormProps {
  draft: AssistantFormState;
  updateField: <K extends keyof AssistantFormState>(field: K, value: AssistantFormState[K]) => void;
}

export const AssistantBehaviorForm: React.FC<AssistantBehaviorFormProps> = ({
  draft,
  updateField,
}) => {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-5 space-y-4 shadow-xs">
      <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3">
        <Sliders className="w-4 h-4 text-[var(--color-purple)]" />
        <h2 className="text-xs font-semibold text-[var(--text-primary)] uppercase tracking-wider">
          Behavior &amp; Grounding Instructions
        </h2>
      </div>

      {/* Enabled / Disabled Switch */}
      <div className="flex items-center justify-between p-3.5 bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl">
        <div className="flex items-start gap-3">
          <div
            className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
              draft.is_enabled
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                : 'bg-[var(--surface)] text-[var(--text-muted)] border border-[var(--border)]'
            }`}
          >
            <Power className="w-3.5 h-3.5" />
          </div>
          <div>
            <span className="text-xs font-medium text-[var(--text-primary)] block">
              Assistant Active State
            </span>
            <span className="text-[11px] text-[var(--text-secondary)]">
              When disabled, the assistant widget is hidden from your storefront visitors.
            </span>
          </div>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={draft.is_enabled}
          onClick={() => updateField('is_enabled', !draft.is_enabled)}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[var(--color-purple)] ${
            draft.is_enabled ? 'bg-[var(--color-purple)]' : 'bg-zinc-600 dark:bg-zinc-700'
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
              draft.is_enabled ? 'translate-x-4' : 'translate-x-0'
            }`}
          />
        </button>
      </div>

      {/* Advanced System Instructions */}
      <div className="space-y-1.5 pt-1">
        <div className="flex justify-between items-center">
          <label className="text-xs font-medium text-[var(--text-primary)] flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-[var(--color-purple)]" />
            Advanced System Instructions (Optional)
          </label>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            {draft.system_instructions.length}/5000
          </span>
        </div>
        <textarea
          rows={3}
          value={draft.system_instructions}
          maxLength={5000}
          onChange={(e) => updateField('system_instructions', e.target.value)}
          placeholder="e.g. Always respond concisely. If a visitor asks about discount codes, refer them to our seasonal promotions newsletter."
          className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--color-purple)] transition-colors resize-none"
        />
        <div className="text-[11px] text-[var(--text-secondary)] bg-[var(--surface-elevated)] p-3 rounded-xl border border-[var(--border)] space-y-1">
          <p className="font-semibold text-[var(--text-primary)]">Behavioral Guardrails &amp; Blueprint:</p>
          <p>
            System instructions define the persona and boundaries compiled into the assistant&apos;s runtime blueprint. When Integration (Stage 4) builds the repository changes, these guardrails govern customer responses.
          </p>
        </div>
      </div>
    </div>
  );
};
