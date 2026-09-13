'use client';

import React from 'react';
import { FolderGit2, Key, CheckCircle2, Save, Trash2 } from 'lucide-react';
import { IntegrationFormState } from '../types';
import { WebsiteIntegrationConfig } from '@/lib/api/integration';

interface RepositoryConnectionFormProps {
  form: IntegrationFormState;
  config: WebsiteIntegrationConfig | null;
  isSaving: boolean;
  onFieldChange: <K extends keyof IntegrationFormState>(key: K, value: IntegrationFormState[K]) => void;
  onSave: () => void;
  onDelete?: () => void;
}

export const RepositoryConnectionForm: React.FC<RepositoryConnectionFormProps> = ({
  form,
  config,
  isSaving,
  onFieldChange,
  onSave,
  onDelete,
}) => {
  const isEditing = !!config;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl p-6 space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <FolderGit2 className="w-4 h-4 text-zinc-300" />
            Repository Connection &amp; Target
          </h3>
          <p className="text-xs text-zinc-400 mt-0.5">
            Configure the website repository where the assistant widget will be integrated.
          </p>
        </div>
        {config?.has_credentials && (
          <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2.5 py-1 rounded-md">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Token Encrypted
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Owner */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-zinc-300">GitHub Owner / Org</label>
          <input
            type="text"
            required
            value={form.repository_owner}
            onChange={(e) => onFieldChange('repository_owner', e.target.value)}
            placeholder="e.g. acme-corp"
            className="w-full bg-zinc-950/80 border border-zinc-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
          />
        </div>

        {/* Repo */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-zinc-300">Repository Name</label>
          <input
            type="text"
            required
            value={form.repository_name}
            onChange={(e) => onFieldChange('repository_name', e.target.value)}
            placeholder="e.g. storefront-web"
            className="w-full bg-zinc-950/80 border border-zinc-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
          />
        </div>

        {/* Default Branch */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-zinc-300">Default Branch</label>
          <input
            type="text"
            required
            value={form.default_branch}
            onChange={(e) => onFieldChange('default_branch', e.target.value)}
            placeholder="main"
            className="w-full bg-zinc-950/80 border border-zinc-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
          />
        </div>

        {/* Root Dir */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-zinc-300">Website Root Directory</label>
          <input
            type="text"
            value={form.website_root_dir}
            onChange={(e) => onFieldChange('website_root_dir', e.target.value)}
            placeholder="/"
            className="w-full bg-zinc-950/80 border border-zinc-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
          />
        </div>
      </div>

      <p className="text-[11px] text-zinc-500 leading-relaxed">
        The framework, app shell and integration point are detected from the repository by the
        analyst. No framework selection or target path is required.
      </p>

      {/* GitHub Access Token */}
      <div className="space-y-1.5 pt-2 border-t border-zinc-800/80">
        <label className="text-xs font-semibold text-zinc-300 flex items-center gap-1.5">
          <Key className="w-3.5 h-3.5 text-zinc-400" />
          GitHub Personal Access Token (PAT)
        </label>
        <input
          type="password"
          value={form.github_token}
          onChange={(e) => onFieldChange('github_token', e.target.value)}
          placeholder={config?.has_credentials ? '•••••••••••••••••••••••• (Leave blank to keep existing)' : 'ghp_...'}
          className="w-full bg-zinc-950/80 border border-zinc-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
        />
        <p className="text-[11px] text-zinc-500 leading-relaxed">
          Stored with authenticated encryption (AES-128-CBC / HMAC-SHA256). Token is never displayed or returned via API.
        </p>
      </div>

      {/* Action buttons */}
      <div className="flex items-center justify-between pt-2">
        {isEditing && onDelete ? (
          <button
            type="button"
            onClick={onDelete}
            className="px-3 py-2 rounded-xl text-xs font-semibold text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 transition-colors flex items-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Delete Connection
          </button>
        ) : (
          <div />
        )}

        <button
          type="submit"
          disabled={isSaving || !form.repository_owner || !form.repository_name}
          className="px-4 py-2.5 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-sm"
        >
          <Save className="w-3.5 h-3.5" />
          {isSaving ? 'Saving...' : isEditing ? 'Update Configuration' : 'Connect Repository'}
        </button>
      </div>
    </form>
  );
};
