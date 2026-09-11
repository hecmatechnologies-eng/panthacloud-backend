'use client';

import React from 'react';
import { useProject } from '../context';
import { StageId } from '../types';
import {
  Home,
  Globe,
  BookOpen,
  Bot,
  Plug,
  Play,
  Activity,
  Settings,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react';

export interface ProjectNavigationProps {
  className?: string;
}

interface NavItem {
  id: StageId;
  label: string;
  icon: React.FC<{ className?: string }>;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const sections: NavSection[] = [
  {
    title: 'BUILD',
    items: [
      { id: 'overview', label: 'Overview', icon: Home },
      { id: 'website', label: 'Website', icon: Globe },
      { id: 'knowledge', label: 'Knowledge', icon: BookOpen },
      { id: 'assistant', label: 'Assistant', icon: Bot },
    ],
  },
  {
    title: 'CONNECT',
    items: [
      { id: 'integration', label: 'Integration', icon: Plug },
    ],
  },
  {
    title: 'LIVE',
    items: [
      { id: 'preview', label: 'Preview', icon: Play },
      { id: 'activity', label: 'Activity', icon: Activity },
    ],
  },
  {
    title: 'PROJECT',
    items: [
      { id: 'settings', label: 'Settings', icon: Settings },
    ],
  },
];

export const ProjectNavigation: React.FC<ProjectNavigationProps> = ({
  className = '',
}) => {
  const {
    currentProject,
    activeItem,
    setActiveItem,
    selectProject,
    isStageCompleted,
    isStageActionable,
    pinStage,
    previewStageId,
    setPreviewStageId,
  } = useProject();

  const projectInitial = (currentProject?.name || 'P').charAt(0).toUpperCase();

  return (
    <nav
      data-testid="project-navigation"
      aria-label="Project lifecycle navigation"
      className={`w-56 sm:w-60 shrink-0 rounded-2xl bg-[var(--surface)] border border-[var(--border)] shadow-xs p-3.5 flex flex-col justify-between text-[var(--text-primary)] transition-colors select-none ${className}`}
    >
      <div className="space-y-4">
        {/* Project Card Header */}
        {currentProject && (
          <div
            data-testid="project-nav-header"
            className="flex items-center justify-between p-2 rounded-xl bg-[var(--surface-elevated)] border border-[var(--border)]/70 transition-colors"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-lg bg-emerald-950 text-emerald-400 font-bold flex items-center justify-center text-xs shrink-0 shadow-xs">
                {projectInitial}
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-[var(--text-primary)] truncate">
                  {currentProject.name}
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-[var(--text-muted)] font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                  <span>Active</span>
                </div>
              </div>
            </div>

            <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
          </div>
        )}

        {/* Navigation Sections */}
        {sections.map((section, idx) => (
          <div key={section.title} className="space-y-1">
            <div className="px-2 py-0.5 text-[10px] font-mono font-medium text-[var(--text-muted)] tracking-wider">
              {section.title}
            </div>

            <div className="space-y-0.5">
              {section.items.map(({ id, label, icon: Icon }) => {
                const isActive = activeItem === id;
                const isCompleted = isStageCompleted(id);
                const isActionable = isStageActionable(id);

                return (
                  <div
                    key={id}
                    className="relative"
                    onMouseEnter={() => setPreviewStageId(id)}
                    onMouseLeave={() => setPreviewStageId(null)}
                  >
                  <button
                    type="button"
                    data-testid={`nav-${id}`}
                    onClick={() => setActiveItem(id)}
                    className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-xl text-xs transition-colors cursor-pointer text-left group ${
                      isActive
                        ? 'text-purple-700 dark:text-purple-300 bg-purple-100/70 dark:bg-purple-950/40 font-semibold'
                        : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)]'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Icon
                        className={`w-3.5 h-3.5 shrink-0 transition-colors ${
                          isActive
                            ? 'text-purple-600 dark:text-purple-400'
                            : 'text-[var(--text-muted)] group-hover:text-[var(--text-primary)]'
                        }`}
                      />
                      <span className="truncate">{label}</span>
                    </div>

                    <div className="shrink-0 flex items-center pl-2">
                      {isActive && (
                        <span
                          data-testid={`status-dot-active-${id}`}
                          className="w-1.5 h-1.5 rounded-full bg-[var(--color-purple)]"
                        />
                      )}

                      {!isActive && isCompleted && (
                        <span
                          data-testid={`status-completed-${id}`}
                          className="w-1.5 h-1.5 rounded-full bg-emerald-500"
                        />
                      )}

                      {!isActive && !isCompleted && !isActionable && (
                        <span
                          data-testid={`status-waiting-${id}`}
                          title="Waiting for prerequisite"
                          className="w-1.5 h-1.5 rounded-full border border-[var(--border)] group-hover:border-[var(--text-muted)] transition-colors"
                        />
                      )}

                      {!isActive && !isCompleted && isActionable && id !== 'overview' && id !== 'settings' && (
                        <span
                          data-testid={`status-actionable-${id}`}
                          title="Ready to configure"
                          className="w-1.5 h-1.5 rounded-full bg-[var(--text-muted)]/60"
                        />
                      )}
                    </div>
                  </button>
                  {id !== 'overview' && (
                    <button
                      type="button"
                      aria-label={`Pin ${label} in workspace`}
                      data-testid={`pin-stage-${id}`}
                      onClick={() => pinStage(id)}
                      className="absolute right-1.5 top-1/2 hidden h-4 w-4 -translate-y-1/2 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface)] hover:text-[var(--color-purple)] group-hover:flex"
                    >
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {previewStageId === id && id !== 'overview' && (
                    <div data-testid={`stage-preview-${id}`} className="absolute left-[calc(100%+0.5rem)] top-0 z-20 hidden w-56 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3 shadow-lg md:block">
                      <div className="text-xs font-semibold text-[var(--text-primary)]">{label}</div>
                      <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">Open this stage in the workspace to keep its progress and system activity in view.</p>
                      <button type="button" onClick={() => pinStage(id)} className="mt-2 text-[11px] font-medium text-[var(--color-purple)] hover:underline cursor-pointer">Pin to workspace</button>
                    </div>
                  )}
                  </div>
                );
              })}
            </div>

            {idx < sections.length - 1 && (
              <div className="pt-2 border-b border-[var(--border)]/60" />
            )}
          </div>
        ))}
      </div>

      {/* Bottom Action: Return to Workspace / Projects List */}
      <div className="pt-3 mt-4 border-t border-[var(--border)]/60">
        <button
          type="button"
          data-testid="nav-all-projects"
          onClick={() => selectProject(null)}
          className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-xl text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)] transition-colors cursor-pointer group"
        >
          <ChevronLeft className="w-3.5 h-3.5 transition-transform group-hover:-translate-x-0.5" />
          <span>All projects</span>
        </button>
      </div>
    </nav>
  );
};
