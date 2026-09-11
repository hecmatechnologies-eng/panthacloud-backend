'use client';

import React from 'react';
import { IntegrationProvider } from '@/lib/api';

interface NewIntegrationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  name: string;
  setName: (val: string) => void;
  provider: IntegrationProvider;
  setProvider: (val: IntegrationProvider) => void;
  repo: string;
  setRepo: (val: string) => void;
}

export const NewIntegrationModal: React.FC<NewIntegrationModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  name,
  setName,
  provider,
  setProvider,
  repo,
  setRepo,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
      <form
        onSubmit={onSubmit}
        className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-sm w-full space-y-4 shadow-2xl"
      >
        <h3 className="text-sm font-semibold text-white">Connect External Integration</h3>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Integration Name</label>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Production GitHub"
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Provider</label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as IntegrationProvider)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="github">GitHub</option>
            <option value="gitlab">GitLab</option>
            <option value="external_api">External API</option>
            <option value="webhook">Webhook</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Repository / Resource Target</label>
          <input
            type="text"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="e.g. org/repo-name"
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium"
          >
            Connect
          </button>
        </div>
      </form>
    </div>
  );
};
