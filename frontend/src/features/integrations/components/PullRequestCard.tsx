'use client';

import React from 'react';
import { GitPullRequest, ExternalLink, GitBranch, ShieldCheck } from 'lucide-react';
import { PullRequestInfo } from '@/lib/api/integration';

interface PullRequestCardProps {
  pr: PullRequestInfo;
}

export const PullRequestCard: React.FC<PullRequestCardProps> = ({ pr }) => {
  return (
    <div className="bg-gradient-to-br from-emerald-950/40 via-zinc-900/80 to-zinc-950 border border-emerald-800/60 rounded-2xl p-6 space-y-4 shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-emerald-600/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
            <GitPullRequest className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>{pr.title}</span>
              <span className="text-xs font-mono font-normal text-emerald-400">
                #{pr.pull_request_number}
              </span>
            </h3>
            <p className="text-xs text-zinc-400 flex items-center gap-1 mt-0.5 font-mono">
              <GitBranch className="w-3.5 h-3.5 text-zinc-500" />
              <span>{pr.branch_name}</span>
              <span className="text-zinc-600">→</span>
              <span className="text-zinc-300">{pr.base_branch}</span>
            </p>
          </div>
        </div>

        {pr.pull_request_url && (
          <a
            href={pr.pull_request_url}
            target="_blank"
            rel="noreferrer"
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 transition-all flex items-center gap-1.5 shrink-0 shadow-md"
          >
            <span>Review on GitHub</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>

      <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-xl p-3.5 flex items-start gap-3">
        <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
        <p className="text-xs text-zinc-300 leading-relaxed">
          <strong>Production Safety Notice:</strong> This integration has been safely applied to a dedicated branch. 
          Your production website remains untouched until your engineering team reviews and merges this Pull Request.
        </p>
      </div>
    </div>
  );
};
