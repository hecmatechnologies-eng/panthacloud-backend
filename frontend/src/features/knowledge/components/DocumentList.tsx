'use client';

import React, { useState } from 'react';
import { Eye, FileText, Loader2, Trash2 } from 'lucide-react';
import { KnowledgeDocument } from '../types';
import { DocumentStatusBadge } from './DocumentStatusBadge';

interface DocumentListProps {
  documents: KnowledgeDocument[];
  isLoading: boolean;
  onInspect: (doc: KnowledgeDocument) => void;
  onDelete: (docId: string) => Promise<void>;
}

export const DocumentList: React.FC<DocumentListProps> = ({
  documents,
  isLoading,
  onInspect,
  onDelete,
}) => {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getFormatType = (filename: string, contentType: string) => {
    if (filename.endsWith('.pdf') || contentType.includes('pdf')) return 'PDF';
    if (filename.endsWith('.md') || contentType.includes('markdown')) return 'Markdown';
    return 'Plain Text';
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (window.confirm(`Are you sure you want to delete '${filename}'? This will remove all associated chunks and citations.`)) {
      setDeletingId(docId);
      try {
        await onDelete(docId);
      } finally {
        setDeletingId(null);
      }
    }
  };

  if (isLoading && documents.length === 0) {
    return (
      <div className="p-8 text-center bg-[var(--surface-elevated)]/40 border border-[var(--border)] rounded-2xl sm:rounded-3xl space-y-2">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-purple)] mx-auto" />
        <p className="text-xs text-[var(--text-muted)]">Loading knowledge documents...</p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="p-10 text-center bg-[var(--surface-elevated)]/40 border border-[var(--border)] rounded-2xl sm:rounded-3xl space-y-2">
        <FileText className="w-8 h-8 text-[var(--text-muted)] mx-auto opacity-60" />
        <p className="text-sm font-semibold text-[var(--text-primary)]">No knowledge documents yet</p>
        <p className="text-xs text-[var(--text-secondary)] max-w-sm mx-auto">
          Upload PDF manuals, Markdown policies, or text FAQs above to begin grounding your assistant.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[var(--surface-elevated)] border border-[var(--border)] rounded-2xl sm:rounded-3xl overflow-hidden shadow-xs">
      <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5 bg-[var(--surface)]/50">
        <h2 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
          Grounded Documents
        </h2>
        <span className="text-xs text-[var(--text-muted)] font-mono">
          {documents.length} {documents.length === 1 ? 'document' : 'documents'}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-[var(--text-secondary)]">
          <thead className="bg-[var(--surface)] text-[var(--text-muted)] font-medium border-b border-[var(--border)]">
            <tr>
              <th className="px-5 py-3">Document</th>
              <th className="px-4 py-3">Format</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Chunks</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]/60 font-sans">
            {documents.map((doc) => (
              <tr
                key={doc.id}
                className="hover:bg-[var(--surface)]/70 transition-colors group"
              >
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-2.5">
                    <FileText className="w-4 h-4 text-[var(--color-purple)] shrink-0" />
                    <span className="font-medium text-[var(--text-primary)] group-hover:text-[var(--color-purple)] transition-colors">
                      {doc.filename}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3.5 font-mono text-[11px] text-[var(--text-muted)]">
                  {getFormatType(doc.filename, doc.content_type)}
                </td>
                <td className="px-4 py-3.5 font-mono text-[11px] text-[var(--text-muted)]">
                  {formatSize(doc.file_size_bytes)}
                </td>
                <td className="px-4 py-3.5 font-mono text-[11px] text-[var(--text-primary)] font-semibold">
                  {doc.chunks_count}
                </td>
                <td className="px-4 py-3.5">
                  <DocumentStatusBadge status={doc.status} />
                </td>
                <td className="px-4 py-3.5 font-mono text-[11px] text-[var(--text-muted)]">
                  {new Date(doc.created_at).toLocaleDateString()}
                </td>
                <td className="px-5 py-3.5 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={() => onInspect(doc)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[var(--surface)] hover:bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--text-primary)] text-xs transition-colors cursor-pointer"
                      title="Inspect Chunks and Citations"
                    >
                      <Eye className="w-3.5 h-3.5 text-[var(--color-purple)]" />
                      Inspect
                    </button>
                    <button
                      onClick={() => handleDelete(doc.id, doc.filename)}
                      disabled={deletingId === doc.id}
                      className="inline-flex items-center gap-1 p-1.5 rounded-lg bg-[var(--surface)] hover:bg-rose-500/10 hover:text-rose-600 dark:hover:text-rose-400 border border-[var(--border)] hover:border-rose-500/30 text-[var(--text-muted)] text-xs transition-colors disabled:opacity-50 cursor-pointer"
                      title="Delete Document"
                      aria-label={`Delete ${doc.filename}`}
                    >
                      {deletingId === doc.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-500" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
