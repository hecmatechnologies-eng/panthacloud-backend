'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useProject } from '../context';
import { Layers, Loader2, X } from 'lucide-react';

export const CreateProjectModal: React.FC = () => {
  const { isCreateModalOpen, closeCreateModal, createProject } = useProject();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isCreateModalOpen) {
      setName('');
      setDescription('');
      setErrorMessage(null);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isCreateModalOpen]);

  if (!isCreateModalOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setErrorMessage('Project name is required');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await createProject({
        name: name.trim(),
        description: description.trim() || undefined,
      });
    } catch (err: any) {
      setErrorMessage(err?.message || 'Failed to create project. Please try again.');
      setIsSubmitting(false);
    }
  };

  return (
    <div
      data-testid="create-project-modal"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) closeCreateModal();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-project-title"
    >
      <div
        className="w-full max-w-md rounded-2xl bg-[var(--surface)] border border-[var(--border)] shadow-2xl p-6 space-y-5 text-[var(--text-primary)] transition-colors"
        onKeyDown={(e) => {
          if (e.key === 'Escape') closeCreateModal();
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[var(--color-purple)]/10 flex items-center justify-center text-[var(--color-purple)]">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h2 id="create-project-title" className="text-base font-semibold text-[var(--text-primary)]">
                Create a project
              </h2>
              <p className="text-xs text-[var(--text-secondary)]">
                Give your assistant a home.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={closeCreateModal}
            aria-label="Close dialog"
            className="p-1 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)] transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Error Banner */}
        {errorMessage && (
          <div
            data-testid="create-project-error"
            className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-500 font-medium"
          >
            {errorMessage}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--text-primary)]">
              Project name <span className="text-red-500">*</span>
            </label>
            <input
              ref={inputRef}
              data-testid="project-name-input"
              type="text"
              required
              disabled={isSubmitting}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Website Assistant"
              className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl px-3.5 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-purple)]/50 transition-all"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--text-secondary)]">
              Description <span className="text-[10px] text-[var(--text-muted)]">(optional)</span>
            </label>
            <textarea
              data-testid="project-desc-input"
              rows={2}
              disabled={isSubmitting}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What will this assistant help with?"
              className="w-full bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl px-3.5 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-purple)]/50 transition-all resize-none"
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-2">
            <button
              type="button"
              data-testid="create-project-cancel"
              disabled={isSubmitting}
              onClick={closeCreateModal}
              className="px-4 py-2 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)] rounded-xl transition-colors cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="submit"
              data-testid="create-project-submit"
              disabled={isSubmitting || !name.trim()}
              className="px-4 py-2 text-xs font-medium text-white bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl shadow-sm transition-all cursor-pointer flex items-center gap-1.5"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Creating...</span>
                </>
              ) : (
                <span>Create project</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
