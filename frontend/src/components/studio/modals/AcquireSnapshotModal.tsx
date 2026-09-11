'use client';

import React from 'react';
import { FolderGit2 } from 'lucide-react';

interface AcquireSnapshotModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  branch: string;
  setBranch: (val: string) => void;
  isAcquiring: boolean;
}

export const AcquireSnapshotModal: React.FC<AcquireSnapshotModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  branch,
  setBranch,
  isAcquiring,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
      <form
        onSubmit={onSubmit}
        className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-sm w-full space-y-4 shadow-2xl"
      >
        <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
          <FolderGit2 className="w-4 h-4 text-indigo-400" />
          Acquire Source Snapshot
        </h3>
        <p className="text-xs text-zinc-400">
          Allocate an isolated workspace and checkout a deterministic Git revision.
        </p>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Target Branch / Revision</label>
          <input
            type="text"
            required
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
            disabled={isAcquiring}
            className="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium disabled:opacity-50"
          >
            {isAcquiring ? 'Acquiring...' : 'Acquire Revision'}
          </button>
        </div>
      </form>
    </div>
  );
};
