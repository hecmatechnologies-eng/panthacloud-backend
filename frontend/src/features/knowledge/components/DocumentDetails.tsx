'use client';

import React from 'react';
import { AlertCircle, BookOpen, Calendar, FileText, HardDrive, Layers, X } from 'lucide-react';
import { KnowledgeDocument } from '../types';
import { DocumentStatusBadge } from './DocumentStatusBadge';
import { ChunkPreview } from './ChunkPreview';

interface DocumentDetailsProps {
  document: KnowledgeDocument | null;
  onClose: () => void;
}

export const DocumentDetails: React.FC<DocumentDetailsProps> = ({ document, onClose }) => {
  if (!document) return null;

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-3xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden text-left">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border)] p-6 bg-[var(--surface-elevated)]/40">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-2xl bg-purple-100/70 dark:bg-purple-950/60 border border-purple-200/80 dark:border-purple-900/50 flex items-center justify-center text-[var(--color-purple)] shrink-0 shadow-xs">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-[var(--text-primary)] tracking-tight flex items-center gap-2">
                {document.filename}
              </h2>
              <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] mt-0.5 font-mono">
                <span>{document.content_type}</span>
                <span>•</span>
                <span>{formatSize(document.file_size_bytes)}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <DocumentStatusBadge status={document.status} />
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)] transition-colors cursor-pointer"
              aria-label="Close modal"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Metadata Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="bg-[var(--surface-elevated)] border border-[var(--border)] p-3.5 rounded-2xl space-y-1">
              <span className="text-[var(--text-muted)] flex items-center gap-1 font-mono uppercase text-[10px] tracking-wider">
                <Layers className="w-3.5 h-3.5 text-[var(--color-purple)]" />
                Chunks
              </span>
              <p className="font-mono font-bold text-[var(--text-primary)] text-sm">{document.chunks_count}</p>
            </div>
            <div className="bg-[var(--surface-elevated)] border border-[var(--border)] p-3.5 rounded-2xl space-y-1">
              <span className="text-[var(--text-muted)] flex items-center gap-1 font-mono uppercase text-[10px] tracking-wider">
                <HardDrive className="w-3.5 h-3.5 text-indigo-500" />
                Size
              </span>
              <p className="font-mono font-bold text-[var(--text-primary)] text-sm">{formatSize(document.file_size_bytes)}</p>
            </div>
            <div className="bg-[var(--surface-elevated)] border border-[var(--border)] p-3.5 rounded-2xl space-y-1">
              <span className="text-[var(--text-muted)] flex items-center gap-1 font-mono uppercase text-[10px] tracking-wider">
                <BookOpen className="w-3.5 h-3.5 text-emerald-500" />
                Type
              </span>
              <p className="font-mono font-bold text-[var(--text-primary)] text-xs truncate">{document.content_type}</p>
            </div>
            <div className="bg-[var(--surface-elevated)] border border-[var(--border)] p-3.5 rounded-2xl space-y-1">
              <span className="text-[var(--text-muted)] flex items-center gap-1 font-mono uppercase text-[10px] tracking-wider">
                <Calendar className="w-3.5 h-3.5 text-amber-500" />
                Uploaded
              </span>
              <p className="font-mono text-[var(--text-secondary)] text-[11px] truncate">
                {new Date(document.created_at).toLocaleDateString()}
              </p>
            </div>
          </div>

          {/* Failure Alert if any */}
          {document.status === 'FAILED' && document.error_message && (
            <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-2xl text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold">Extraction Error:</span>
                <p className="mt-0.5 text-rose-600/90 dark:text-rose-300">{document.error_message}</p>
              </div>
            </div>
          )}

          {/* Extracted Chunks List */}
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-[var(--border)] pb-2.5">
              <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider font-mono">
                Extracted Chunks & Citations
              </h3>
              <span className="text-xs text-[var(--text-muted)] font-mono">
                {document.chunks?.length || 0} chunks persisted
              </span>
            </div>

            {(!document.chunks || document.chunks.length === 0) ? (
              <p className="text-xs text-[var(--text-muted)] italic text-center py-6">
                No chunks available for this document.
              </p>
            ) : (
              <div className="space-y-3">
                {document.chunks.map((chunk) => (
                  <ChunkPreview key={chunk.id} chunk={chunk} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-[var(--border)] p-4 bg-[var(--surface-elevated)]/40 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-[var(--surface-elevated)] hover:bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded-xl text-xs font-semibold transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
