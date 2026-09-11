'use client';

import React, { useState } from 'react';
import { Palette, Layout, Image as ImageIcon, Bot, Check } from 'lucide-react';
import { AssistantFormState } from '../types';
import { AssistantPosition } from '@/lib/api/assistant';

interface AssistantAppearanceFormProps {
  draft: AssistantFormState;
  updateField: <K extends keyof AssistantFormState>(field: K, value: AssistantFormState[K]) => void;
}

const BRAND_PALETTES = [
  { name: 'Indigo', hex: '#6366F1' },
  { name: 'Violet', hex: '#8B5CF6' },
  { name: 'Emerald', hex: '#10B981' },
  { name: 'Blue', hex: '#3B82F6' },
  { name: 'Rose', hex: '#F43F5E' },
  { name: 'Amber', hex: '#F59E0B' },
  { name: 'Slate', hex: '#64748B' },
  { name: 'Zinc', hex: '#27272A' },
];

const TEXT_PALETTES = [
  { name: 'White', hex: '#FFFFFF' },
  { name: 'Light', hex: '#F8FAFC' },
  { name: 'Dark', hex: '#18181B' },
  { name: 'Black', hex: '#000000' },
];

export const AssistantAppearanceForm: React.FC<AssistantAppearanceFormProps> = ({
  draft,
  updateField,
}) => {
  const [avatarError, setAvatarError] = useState(false);

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-5 space-y-5 shadow-xs">
      <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3">
        <Palette className="w-4 h-4 text-[var(--color-purple)]" />
        <h2 className="text-xs font-semibold text-[var(--text-primary)] uppercase tracking-wider">
          Appearance &amp; Widget Styling
        </h2>
      </div>

      {/* Brand Accent Color */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-[var(--text-primary)]">
          Brand Accent Color
        </label>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          {BRAND_PALETTES.map((p) => (
            <button
              key={p.hex}
              type="button"
              onClick={() => updateField('brand_color', p.hex)}
              className="w-6 h-6 rounded-md border border-[var(--border)] flex items-center justify-center transition-transform hover:scale-110 relative cursor-pointer"
              style={{ backgroundColor: p.hex }}
              title={p.name}
            >
              {draft.brand_color.toUpperCase() === p.hex.toUpperCase() && (
                <Check className="w-3.5 h-3.5 text-white stroke-[3]" />
              )}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <input
            type="color"
            value={draft.brand_color.startsWith('#') && draft.brand_color.length === 7 ? draft.brand_color : '#6366F1'}
            onChange={(e) => updateField('brand_color', e.target.value.toUpperCase())}
            className="w-8 h-8 rounded-lg border border-[var(--border)] cursor-pointer bg-[var(--surface-elevated)] p-0.5"
          />
          <input
            type="text"
            value={draft.brand_color}
            maxLength={7}
            onChange={(e) => updateField('brand_color', e.target.value)}
            className="w-28 bg-[var(--surface-elevated)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-xs font-mono text-[var(--text-primary)] focus:outline-none focus:border-[var(--color-purple)] uppercase"
            placeholder="#6366F1"
          />
          <span className="text-[11px] text-[var(--text-secondary)]">
            Controls the launcher button, header bar, and accents.
          </span>
        </div>
      </div>

      {/* Header Text Color */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-[var(--text-primary)]">
          Header Text Color
        </label>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          {TEXT_PALETTES.map((p) => (
            <button
              key={p.hex}
              type="button"
              onClick={() => updateField('text_color', p.hex)}
              className="w-6 h-6 rounded-md border border-[var(--border)] flex items-center justify-center transition-transform hover:scale-110 cursor-pointer"
              style={{ backgroundColor: p.hex }}
              title={p.name}
            >
              {draft.text_color.toUpperCase() === p.hex.toUpperCase() && (
                <Check
                  className={`w-3.5 h-3.5 stroke-[3] ${
                    p.hex === '#FFFFFF' || p.hex === '#F8FAFC' ? 'text-zinc-900' : 'text-white'
                  }`}
                />
              )}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <input
            type="color"
            value={draft.text_color.startsWith('#') && draft.text_color.length === 7 ? draft.text_color : '#FFFFFF'}
            onChange={(e) => updateField('text_color', e.target.value.toUpperCase())}
            className="w-8 h-8 rounded-lg border border-[var(--border)] cursor-pointer bg-[var(--surface-elevated)] p-0.5"
          />
          <input
            type="text"
            value={draft.text_color}
            maxLength={7}
            onChange={(e) => updateField('text_color', e.target.value)}
            className="w-28 bg-[var(--surface-elevated)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-xs font-mono text-[var(--text-primary)] focus:outline-none focus:border-[var(--color-purple)] uppercase"
            placeholder="#FFFFFF"
          />
          <span className="text-[11px] text-[var(--text-secondary)]">
            Foreground color for contrast against the brand header.
          </span>
        </div>
      </div>

      {/* Screen Position */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-[var(--text-primary)] flex items-center gap-1.5">
          <Layout className="w-3.5 h-3.5 text-[var(--color-purple)]" />
          Widget Screen Position
        </label>
        <div className="grid grid-cols-2 gap-3 max-w-sm">
          <button
            type="button"
            onClick={() => updateField('position', 'BOTTOM_RIGHT')}
            className={`flex items-center justify-center gap-2 p-2.5 rounded-xl border text-xs font-medium transition-all cursor-pointer ${
              draft.position === 'BOTTOM_RIGHT'
                ? 'bg-violet-950/60 border-violet-600 text-violet-200 shadow-xs'
                : 'bg-[var(--surface-elevated)] border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border)]/80'
            }`}
          >
            <div className="w-3.5 h-3.5 border border-current rounded-sm flex items-end justify-end p-0.5">
              <span className="w-1 h-1 bg-current rounded-full" />
            </div>
            <span>Bottom Right</span>
          </button>

          <button
            type="button"
            onClick={() => updateField('position', 'BOTTOM_LEFT')}
            className={`flex items-center justify-center gap-2 p-2.5 rounded-xl border text-xs font-medium transition-all cursor-pointer ${
              draft.position === 'BOTTOM_LEFT'
                ? 'bg-violet-950/60 border-violet-600 text-violet-200 shadow-xs'
                : 'bg-[var(--surface-elevated)] border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border)]/80'
            }`}
          >
            <div className="w-3.5 h-3.5 border border-current rounded-sm flex items-end justify-start p-0.5">
              <span className="w-1 h-1 bg-current rounded-full" />
            </div>
            <span>Bottom Left</span>
          </button>
        </div>
      </div>

      {/* Avatar URL */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-[var(--text-primary)] flex items-center gap-1.5">
          <ImageIcon className="w-3.5 h-3.5 text-[var(--color-purple)]" />
          Custom Avatar URL (Optional)
        </label>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-[var(--surface-elevated)] border border-[var(--border)] flex items-center justify-center overflow-hidden shrink-0">
            {draft.avatar_url && !avatarError ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={draft.avatar_url}
                alt="Avatar"
                onError={() => setAvatarError(true)}
                className="w-full h-full object-cover"
              />
            ) : (
              <Bot className="w-4 h-4 text-[var(--text-muted)]" />
            )}
          </div>
          <input
            type="url"
            value={draft.avatar_url}
            maxLength={500}
            onChange={(e) => {
              setAvatarError(false);
              updateField('avatar_url', e.target.value);
            }}
            placeholder="https://example.com/assistant-avatar.png"
            className="flex-1 bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--color-purple)] transition-colors"
          />
        </div>
        <p className="text-[11px] text-[var(--text-secondary)]">
          Must be a secure HTTPS image URL. If omitted, the default assistant icon is used.
        </p>
      </div>
    </div>
  );
};
