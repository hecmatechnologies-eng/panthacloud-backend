'use client';

import React from 'react';
import { Bot, MessageSquare, Sparkles } from 'lucide-react';
import { AssistantFormState } from '../types';

interface AssistantIdentityFormProps {
  draft: AssistantFormState;
  updateField: <K extends keyof AssistantFormState>(field: K, value: AssistantFormState[K]) => void;
}

export const AssistantIdentityForm: React.FC<AssistantIdentityFormProps> = ({
  draft,
  updateField,
}) => {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-5 space-y-4 shadow-xs">
      <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3">
        <Bot className="w-4 h-4 text-[var(--color-purple)]" />
        <h2 className="text-xs font-semibold text-[var(--text-primary)] uppercase tracking-wider">
          Assistant Identity &amp; Voice
        </h2>
      </div>

      {/* Assistant Name */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <label className="text-xs font-medium text-[var(--text-primary)]">
            Assistant Name <span className="text-rose-400">*</span>
          </label>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            {draft.name.length}/100
          </span>
        </div>
        <input
          type="text"
          value={draft.name}
          maxLength={100}
          onChange={(e) => updateField('name', e.target.value)}
          placeholder="e.g. Storefront Concierge"
          className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--color-purple)] transition-colors"
        />
        <p className="text-[11px] text-[var(--text-secondary)]">
          The public display name visitors see in the chat header.
        </p>
      </div>

      {/* Description */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <label className="text-xs font-medium text-[var(--text-primary)]">Description</label>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            {draft.description.length}/1000
          </span>
        </div>
        <input
          type="text"
          value={draft.description}
          maxLength={1000}
          onChange={(e) => updateField('description', e.target.value)}
          placeholder="e.g. Helps customers with product sizing, orders, and returns"
          className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--color-purple)] transition-colors"
        />
        <p className="text-[11px] text-[var(--text-secondary)]">
          Internal description of the assistant&apos;s role.
        </p>
      </div>

      {/* Welcome Message */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <label className="text-xs font-medium text-[var(--text-primary)]">
            Welcome Greeting <span className="text-rose-400">*</span>
          </label>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            {draft.welcome_message.length}/1000
          </span>
        </div>
        <textarea
          rows={3}
          value={draft.welcome_message}
          maxLength={1000}
          onChange={(e) => updateField('welcome_message', e.target.value)}
          placeholder="e.g. Hi there! How can I help you find the right product today?"
          className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--color-purple)] transition-colors resize-none"
        />
        <p className="text-[11px] text-[var(--text-secondary)]">
          Initial greeting message automatically displayed when the visitor opens the widget.
        </p>
      </div>

      {/* Starter Prompt */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <label className="text-xs font-medium text-[var(--text-primary)] flex items-center gap-1.5">
            <MessageSquare className="w-3.5 h-3.5 text-[var(--color-purple)]" />
            Suggested Starter Prompt
          </label>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            {draft.starter_prompt.length}/500
          </span>
        </div>
        <input
          type="text"
          value={draft.starter_prompt}
          maxLength={500}
          onChange={(e) => updateField('starter_prompt', e.target.value)}
          placeholder="e.g. What are your shipping and return policies?"
          className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--color-purple)] transition-colors"
        />
        <p className="text-[11px] text-[var(--text-secondary)]">
          Clickable prompt chip displayed below the welcome message to guide user queries.
        </p>
      </div>
    </div>
  );
};
