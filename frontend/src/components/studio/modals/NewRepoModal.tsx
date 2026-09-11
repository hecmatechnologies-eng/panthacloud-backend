'use client';

import React from 'react';
import { Integration } from '@/lib/api';

interface NewRepoModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  integrations: Integration[];
  integrationId: string;
  setIntegrationId: (val: string) => void;
  name: string;
  setName: (val: string) => void;
  fullName: string;
  setFullName: (val: string) => void;
  externalId: string;
  setExternalId: (val: string) => void;
  branch: string;
  setBranch: (val: string) => void;
}

export const NewRepoModal: React.FC<NewRepoModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  integrations,
  integrationId,
  setIntegrationId,
  name,
  setName,
  fullName,
  setFullName,
  externalId,
  setExternalId,
  branch,
  setBranch,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
      <form
        onSubmit={onSubmit}
        className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-sm w-full space-y-4 shadow-2xl"
      >
        <h3 className="text-sm font-semibold text-white">Register Source Repository</h3>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Connection Integration</label>
          <select
            value={integrationId}
            onChange={(e) => setIntegrationId(e.target.value)}
            required
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" disabled>
              Select Integration
            </option>
            {integrations.map((integ) => (
              <option key={integ.id} value={integ.id}>
                {integ.name} ({integ.provider})
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Repository Name</label>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. website-frontend"
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Full Name (Owner / Repo)</label>
          <input
            type="text"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="e.g. acme/website-frontend"
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">External ID</label>
          <input
            type="text"
            required
            value={externalId}
            onChange={(e) => setExternalId(e.target.value)}
            placeholder="e.g. 10293847"
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Default Branch</label>
          <input
            type="text"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="main"
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
            Register
          </button>
        </div>
      </form>
    </div>
  );
};
