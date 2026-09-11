'use client';

import React from 'react';
import { Bookmark, Hash } from 'lucide-react';
import { KnowledgeChunk } from '../types';

interface ChunkPreviewProps {
  chunk: KnowledgeChunk;
}

export const ChunkPreview: React.FC<ChunkPreviewProps> = ({ chunk }) => {
  return (
    <div className="bg-[var(--surface-elevated)] border border-[var(--border)] rounded-2xl p-4 space-y-2 hover:border-[var(--color-purple)]/40 transition-colors">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 font-mono text-[11px] bg-[var(--surface)] text-[var(--text-primary)] border border-[var(--border)] px-2.5 py-0.5 rounded-lg font-semibold">
            <Hash className="w-3 h-3 text-[var(--color-purple)]" />
            Chunk {chunk.chunk_index + 1}
          </span>
          {chunk.source_location && (
            <span className="flex items-center gap-1 text-[11px] font-medium bg-purple-500/10 border border-purple-500/20 text-purple-700 dark:text-purple-300 px-2.5 py-0.5 rounded-full">
              <Bookmark className="w-3 h-3 text-[var(--color-purple)]" />
              {chunk.source_location}
            </span>
          )}
        </div>
        <span className="text-[11px] text-[var(--text-muted)] font-mono">
          ~{chunk.token_count} words
        </span>
      </div>
      <p className="text-xs text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap font-sans bg-[var(--surface)] p-3.5 rounded-xl border border-[var(--border)]/60">
        {chunk.text}
      </p>
    </div>
  );
};
