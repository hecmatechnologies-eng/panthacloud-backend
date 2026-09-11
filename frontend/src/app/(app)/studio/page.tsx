'use client';

import React from 'react';
import {
  useProject,
  CreateProjectModal,
  ProjectNavigation,
  ProjectStudioView,
  StageDependencyView,
  WebsiteStageView,
  KnowledgeStageView,
  AssistantStageView,
  GenericStageView,
  StudioStageWorkspace,
} from '@/features/project';
import { Layers, Plus } from 'lucide-react';

export default function StudioPage() {
  const { currentProject, openCreateModal, activeItem, isStageActionable } = useProject();

  return (
    <>
      <CreateProjectModal />

      {!currentProject ? (
        /* Empty Workspace Entry Point */
        <div
          data-testid="empty-workspace"
          className="flex-1 w-full flex flex-col justify-between py-8 sm:py-12 select-none"
        >
          {/* Top spacer */}
          <div className="h-4" />

          {/* Center Studio Hero */}
          <div className="flex flex-col items-center text-center px-4 max-w-xl mx-auto space-y-4 sm:space-y-6">
            {/* Glowing Purple Brand Mark */}
            <div className="relative group">
              <div className="absolute -inset-1 bg-[var(--color-purple)]/25 rounded-3xl blur-xl opacity-75 dark:opacity-60 transition duration-500" />
              <div className="relative w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-gradient-to-tr from-purple-700 via-[var(--color-purple)] to-indigo-500 flex items-center justify-center shadow-lg shadow-purple-950/30">
                <Layers className="w-7 h-7 sm:w-8 sm:h-8 text-white" />
              </div>
            </div>

            {/* Title & Subtitle */}
            <div className="space-y-2">
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-[var(--text-primary)] transition-colors">
                Welcome to Fussion
              </h1>
              <p className="text-sm sm:text-base text-[var(--text-secondary)] transition-colors max-w-md mx-auto leading-relaxed">
                Your workspace for building powerful AI assistants for your website.
              </p>
            </div>

            {/* Prominent Project Creation Action */}
            <div className="pt-2">
              <button
                type="button"
                data-testid="create-project-trigger"
                onClick={openCreateModal}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white font-medium text-xs shadow-md shadow-purple-950/30 transition-all cursor-pointer group hover:scale-[1.02] active:scale-[0.98]"
              >
                <Plus className="w-4 h-4" />
                <span>Create project</span>
              </button>
            </div>

            {/* Action Hint */}
            <p className="text-xs sm:text-sm text-[var(--text-muted)] transition-colors">
              Start by creating a project when you&apos;re ready.
            </p>
          </div>

          {/* Bottom Status Bar */}
          <div className="w-full flex items-center justify-between px-2 sm:px-4 pt-8 text-[11px] font-mono text-[var(--text-muted)] transition-colors">
            <div>
              <span>Build · Connect · Automate · Live</span>
            </div>

            {/* Status indicator pill */}
            <div
              data-testid="studio-status-badge"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--surface)]/70 border border-[var(--border)] shadow-xs"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] animate-pulse" />
              <span className="text-[var(--text-secondary)] font-medium">Studio</span>
            </div>
          </div>
        </div>
      ) : (
        /* Project Studio Environment (BUILD -> CONNECT -> LIVE) */
        <div
          data-testid="project-studio-layout"
          className="flex-1 w-full flex flex-col justify-between py-6"
        >
          <div className="w-full flex flex-col xl:flex-row items-start gap-6">
            {/* Contextual Construction Lifecycle Navigation */}
            <ProjectNavigation />

            {/* Project Studio Canvas Surface */}
            <div className="min-w-0 flex-1 w-full">
            {activeItem === 'overview' && <ProjectStudioView project={currentProject} />}
            {activeItem === 'website' && <WebsiteStageView project={currentProject} />}
            {activeItem === 'knowledge' &&
              (isStageActionable('knowledge') ? (
                <KnowledgeStageView project={currentProject} />
              ) : (
                <StageDependencyView stageId="knowledge" />
              ))}
            {activeItem === 'assistant' &&
              (isStageActionable('assistant') ? (
                <AssistantStageView project={currentProject} />
              ) : (
                <StageDependencyView stageId="assistant" />
              ))}
            {activeItem !== 'overview' &&
              activeItem !== 'website' &&
              activeItem !== 'knowledge' &&
              activeItem !== 'assistant' &&
              (isStageActionable(activeItem) ? (
                <GenericStageView stageId={activeItem} />
              ) : (
                <StageDependencyView stageId={activeItem} />
              ))}
            </div>
            <StudioStageWorkspace />
          </div>

          {/* Bottom Status Bar */}
          <div className="w-full flex items-center justify-between px-2 sm:px-4 pt-8 text-[11px] font-mono text-[var(--text-muted)] transition-colors">
            <div>
              <span>Build · Connect · Automate · Live</span>
            </div>

            <div
              data-testid="studio-status-badge"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--surface)]/70 border border-[var(--border)] shadow-xs"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] animate-pulse" />
              <span className="text-[var(--text-secondary)] font-medium">Studio</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
