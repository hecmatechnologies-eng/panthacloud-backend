'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useProject } from '../context';
import { ChevronDown, Check, Plus, Folder } from 'lucide-react';

export const ProjectSelector: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { projects, currentProject, selectProject, openCreateModal } = useProject();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  if (!currentProject) return null;

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Trigger Button */}
      <button
        type="button"
        data-testid="project-selector-button"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Select project"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--surface-elevated)] hover:bg-[var(--surface)] border border-[var(--border)] text-xs font-medium text-[var(--text-primary)] transition-all cursor-pointer shadow-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-purple)]/50 group"
      >
        <Folder className="w-3.5 h-3.5 text-[var(--color-purple)]" />
        <span className="max-w-[140px] truncate">{currentProject.name}</span>
        <ChevronDown
          className={`w-3 h-3 text-[var(--text-secondary)] transition-transform duration-150 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          role="menu"
          data-testid="project-selector-dropdown"
          aria-label="Projects list"
          className="absolute left-0 mt-2 w-60 rounded-2xl bg-[var(--surface)] border border-[var(--border)] shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100 transition-colors"
        >
          <div className="px-2.5 py-1 text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider select-none">
            My Projects
          </div>

          <div className="max-h-48 overflow-y-auto space-y-0.5 py-0.5">
            {projects.map((project) => {
              const isSelected = project.id === currentProject.id;
              return (
                <button
                  key={project.id}
                  type="button"
                  role="menuitem"
                  data-testid={`project-option-${project.id}`}
                  onClick={() => {
                    selectProject(project);
                    setIsOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 text-xs rounded-xl transition-colors cursor-pointer text-left ${
                    isSelected
                      ? 'text-[var(--color-purple)] font-semibold bg-[var(--color-purple)]/10'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)]'
                  }`}
                >
                  <span className="truncate">{project.name}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-[var(--color-purple)] shrink-0" />}
                </button>
              );
            })}
          </div>

          <div className="border-t border-[var(--border)]/70 my-1" role="separator" />

          {/* New Project Action */}
          <button
            type="button"
            role="menuitem"
            data-testid="new-project-button"
            onClick={() => {
              setIsOpen(false);
              openCreateModal();
            }}
            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-[var(--color-purple)] hover:bg-[var(--color-purple)]/10 rounded-xl transition-colors font-medium cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New project</span>
          </button>
        </div>
      )}
    </div>
  );
};
