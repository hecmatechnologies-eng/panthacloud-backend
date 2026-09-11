'use client';

import React from 'react';
import {
  Globe,
  GitBranch,
  ShieldCheck,
  Bot,
  BookOpen,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Clock,
} from 'lucide-react';
import { WebsiteIntegrationConfig, IntegrationRun } from '@/lib/api/integration';

interface IntegrationStatusProps {
  config: WebsiteIntegrationConfig | null;
  latestRun: IntegrationRun | null;
}

export const IntegrationStatus: React.FC<IntegrationStatusProps> = ({ config, latestRun }) => {
  const isConnected = !!config;

  return (
    <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-indigo-400" />
          Integration Status
        </h3>
        {isConnected ? (
          <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-950/80 border border-emerald-800/80 text-emerald-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Connected
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-zinc-800/80 border border-zinc-700 text-zinc-400">
            <span className="w-2 h-2 rounded-full bg-zinc-500" />
            Not Connected
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        {/* Repository */}
        <div className="bg-zinc-950/60 border border-zinc-800/70 rounded-xl p-3.5 space-y-1">
          <div className="text-zinc-500 flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5 text-zinc-400" />
            <span>Target Repository</span>
          </div>
          <p className="font-semibold text-white truncate font-mono">
            {config ? `${config.repository_owner}/${config.repository_name}` : '—'}
          </p>
        </div>

        {/* Branch */}
        <div className="bg-zinc-950/60 border border-zinc-800/70 rounded-xl p-3.5 space-y-1">
          <div className="text-zinc-500 flex items-center gap-1.5">
            <GitBranch className="w-3.5 h-3.5 text-zinc-400" />
            <span>Default Branch</span>
          </div>
          <p className="font-semibold text-zinc-300 font-mono truncate">
            {config?.default_branch || '—'}
          </p>
        </div>

        {/* Assistant Blueprint */}
        <div className="bg-zinc-950/60 border border-zinc-800/70 rounded-xl p-3.5 space-y-1">
          <div className="text-zinc-500 flex items-center gap-1.5">
            <Bot className="w-3.5 h-3.5 text-indigo-400" />
            <span>Phase 10 Assistant</span>
          </div>
          <p className="font-semibold text-emerald-300 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Blueprint Ready
          </p>
        </div>

        {/* Knowledge Base */}
        <div className="bg-zinc-950/60 border border-zinc-800/70 rounded-xl p-3.5 space-y-1">
          <div className="text-zinc-500 flex items-center gap-1.5">
            <BookOpen className="w-3.5 h-3.5 text-amber-400" />
            <span>Phase 09 Knowledge</span>
          </div>
          <p className="font-semibold text-zinc-300 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            Grounding Enabled
          </p>
        </div>
      </div>

      {/* Latest Run / PR Summary */}
      {latestRun && (
        <div className="bg-zinc-950/80 border border-zinc-800 rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-400 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-zinc-400" />
              Latest Integration Pipeline
            </span>
            <span
              className={`font-semibold px-2 py-0.5 rounded text-[11px] ${
                latestRun.status === 'PR_CREATED'
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                  : latestRun.status === 'FAILED'
                  ? 'bg-rose-950 text-rose-300 border border-rose-800'
                  : 'bg-zinc-800 text-zinc-300'
              }`}
            >
              {latestRun.status}
            </span>
          </div>

          {latestRun.pull_request_url && (
            <div className="flex items-center justify-between pt-1">
              <span className="text-xs text-zinc-300 font-mono">
                Pull Request #{latestRun.pull_request_number}
              </span>
              <a
                href={latestRun.pull_request_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold underline"
              >
                <span>View on GitHub</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}

          {latestRun.error_message && (
            <div className="flex items-start gap-2 text-xs text-rose-400 bg-rose-950/40 border border-rose-900/50 p-2.5 rounded-lg mt-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <p className="font-mono text-[11px] leading-relaxed">{latestRun.error_message}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
