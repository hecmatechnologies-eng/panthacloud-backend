'use client';

import React from 'react';
import { Project, Repository, RepositorySnapshot, InspectionResult } from '@/lib/api';
import { StudioTabId } from '../StudioNavigation';
import {
  CheckCircle2,
  Circle,
  Clock,
  ArrowRight,
  Globe,
  BookOpen,
  Bot,
  GitPullRequest,
  Activity,
  Layers,
} from 'lucide-react';

interface OverviewTabProps {
  project: Project | undefined;
  repositories: Repository[];
  snapshots: RepositorySnapshot[];
  inspectionResult: InspectionResult | null;
  onNavigate: (tab: StudioTabId) => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
  project,
  repositories,
  snapshots,
  inspectionResult,
  onNavigate,
}) => {
  const hasRepo = repositories.length > 0;
  const currentRepo = repositories[0];
  const activeSnapshot = snapshots.find((s) => s.repository_id === currentRepo?.id) || snapshots[0];
  const detectedFramework = inspectionResult?.frameworks?.[0] || 'Next.js';

  const milestones = [
    {
      step: 1,
      title: 'Project Setup',
      status: 'COMPLETED' as const,
      description: 'Workspace and project boundary initialized',
    },
    {
      step: 2,
      title: 'Website Connected',
      status: hasRepo ? ('COMPLETED' as const) : ('ACTIVE' as const),
      description: hasRepo
        ? `Connected: ${currentRepo.name} (${detectedFramework})`
        : 'Connect your website repository',
    },
    {
      step: 3,
      title: 'Knowledge Base',
      status: 'UPCOMING' as const,
      description: 'Ingest company documents and FAQs (Phase 09)',
    },
    {
      step: 4,
      title: 'Assistant Design',
      status: 'UPCOMING' as const,
      description: 'Configure branding, colors, and greeting (Phase 10)',
    },
    {
      step: 5,
      title: 'Integration & PR',
      status: 'UPCOMING' as const,
      description: 'Sandbox verification and automated Pull Request (Phase 11)',
    },
    {
      step: 6,
      title: 'Live Assistant',
      status: 'UPCOMING' as const,
      description: 'Visitor conversation runtime (Phase 12)',
    },
  ];

  return (
    <div className="space-y-8">
      {/* Welcome Banner */}
      <div className="bg-gradient-to-r from-zinc-900 via-zinc-900/90 to-indigo-950/40 border border-zinc-800 rounded-2xl p-6 sm:p-8 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-indigo-950/70 border border-indigo-800/60 text-[11px] font-mono text-indigo-300">
              <Layers className="w-3.5 h-3.5" />
              <span>Project: {project?.name || 'Active Project'}</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              AI Integration Engineer Workspace
            </h1>
            <p className="text-sm text-zinc-300 leading-relaxed">
              Fussion connects to your website repository, understands your business knowledge,
              and prepares an automated pull request with a branded AI assistant.
            </p>
          </div>

          <div className="flex flex-wrap gap-2.5 shrink-0">
            <button
              onClick={() => onNavigate('website')}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-indigo-950/40 transition-all"
            >
              <span>{hasRepo ? 'Manage Website' : 'Connect Website'}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onNavigate('diagnostics')}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 hover:text-white rounded-xl text-xs font-medium border border-zinc-700 transition-colors"
            >
              <Activity className="w-3.5 h-3.5 text-zinc-400" />
              <span>Diagnostics</span>
            </button>
          </div>
        </div>
      </div>

      {/* Customer Journey Progression Stepper */}
      <div className="bg-zinc-950/60 border border-zinc-800/90 rounded-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-white">Integration Journey</h2>
            <p className="text-xs text-zinc-400">
              Step-by-step path to deploy your verified website assistant.
            </p>
          </div>
          <span className="text-[11px] font-mono text-indigo-400 bg-indigo-950/60 border border-indigo-800 px-2 py-0.5 rounded">
            MVP Flow
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3 pt-2">
          {milestones.map((m) => {
            const isDone = m.status === 'COMPLETED';
            const isActive = m.status === 'ACTIVE';

            return (
              <div
                key={m.step}
                className={`rounded-xl p-3.5 border transition-all ${
                  isDone
                    ? 'bg-emerald-950/20 border-emerald-800/60'
                    : isActive
                    ? 'bg-indigo-950/30 border-indigo-500/70 shadow-sm'
                    : 'bg-zinc-900/50 border-zinc-800/80 opacity-75'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-[10px] font-bold text-zinc-400">
                    STEP {m.step}
                  </span>
                  {isDone ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : isActive ? (
                    <Circle className="w-4 h-4 text-indigo-400 fill-indigo-400/20 animate-pulse" />
                  ) : (
                    <Clock className="w-3.5 h-3.5 text-zinc-400" />
                  )}
                </div>
                <h3 className="font-semibold text-xs text-white mb-1">{m.title}</h3>
                <p className="text-[11px] text-zinc-400 leading-snug">{m.description}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Summary Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Website */}
        <div
          onClick={() => onNavigate('website')}
          className="bg-zinc-900/80 hover:bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-xl p-5 space-y-3 cursor-pointer transition-all group"
        >
          <div className="flex items-center justify-between">
            <div className="w-8 h-8 rounded-lg bg-indigo-950/80 border border-indigo-800 flex items-center justify-center text-indigo-300">
              <Globe className="w-4 h-4" />
            </div>
            <span
              className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded border uppercase ${
                hasRepo
                  ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                  : 'bg-amber-950 text-amber-300 border-amber-800'
              }`}
            >
              {hasRepo ? 'Connected' : 'Action Needed'}
            </span>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white group-hover:text-indigo-300 transition-colors">
              Website Repository
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              {hasRepo
                ? `${currentRepo.name} (${detectedFramework})`
                : 'Connect GitHub/GitLab repository'}
            </p>
          </div>
          <div className="text-[11px] font-mono text-zinc-400 pt-2 border-t border-zinc-800/80 flex items-center justify-between">
            <span>Branch: {activeSnapshot?.branch || 'main'}</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 2: Knowledge Base */}
        <div
          onClick={() => onNavigate('knowledge')}
          className="bg-zinc-900/80 hover:bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-xl p-5 space-y-3 cursor-pointer transition-all group"
        >
          <div className="flex items-center justify-between">
            <div className="w-8 h-8 rounded-lg bg-sky-950/80 border border-sky-800 flex items-center justify-center text-sky-300">
              <BookOpen className="w-4 h-4" />
            </div>
            <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded border uppercase bg-zinc-800 text-zinc-300 border-zinc-700">
              Phase 09
            </span>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white group-hover:text-sky-300 transition-colors">
              Knowledge Base
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">Business documents, FAQs, and manuals</p>
          </div>
          <div className="text-[11px] font-mono text-zinc-400 pt-2 border-t border-zinc-800/80 flex items-center justify-between">
            <span>Coming next</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 3: Assistant Branding */}
        <div
          onClick={() => onNavigate('assistant')}
          className="bg-zinc-900/80 hover:bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-xl p-5 space-y-3 cursor-pointer transition-all group"
        >
          <div className="flex items-center justify-between">
            <div className="w-8 h-8 rounded-lg bg-violet-950/80 border border-violet-800 flex items-center justify-center text-violet-300">
              <Bot className="w-4 h-4" />
            </div>
            <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded border uppercase bg-zinc-800 text-zinc-300 border-zinc-700">
              Phase 10
            </span>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white group-hover:text-violet-300 transition-colors">
              Assistant Branding
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">Widget styling, colors, and welcome prompts</p>
          </div>
          <div className="text-[11px] font-mono text-zinc-400 pt-2 border-t border-zinc-800/80 flex items-center justify-between">
            <span>Coming soon</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 4: Integration Delivery */}
        <div
          onClick={() => onNavigate('integration')}
          className="bg-zinc-900/80 hover:bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-xl p-5 space-y-3 cursor-pointer transition-all group"
        >
          <div className="flex items-center justify-between">
            <div className="w-8 h-8 rounded-lg bg-emerald-950/80 border border-emerald-800 flex items-center justify-center text-emerald-300">
              <GitPullRequest className="w-4 h-4" />
            </div>
            <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded border uppercase bg-zinc-800 text-zinc-300 border-zinc-700">
              Phase 11–12
            </span>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white group-hover:text-emerald-300 transition-colors">
              Pull Request Delivery
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">Automated code integration and live chat</p>
          </div>
          <div className="text-[11px] font-mono text-zinc-400 pt-2 border-t border-zinc-800/80 flex items-center justify-between">
            <span>Pending approval</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>
      </div>
    </div>
  );
};
