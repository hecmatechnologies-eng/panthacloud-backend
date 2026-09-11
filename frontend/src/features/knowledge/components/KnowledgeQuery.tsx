'use client';

import React, { useState } from 'react';
import { AlertCircle, Bookmark, FileText, Loader2, Search, SlidersHorizontal, Sparkles } from 'lucide-react';
import { KnowledgeQueryResultItem } from '../types';

interface KnowledgeQueryProps {
  onQuery: (query: string, topK: number, scoreThreshold: number) => Promise<KnowledgeQueryResultItem[]>;
  isQuerying: boolean;
}

export const KnowledgeQuery: React.FC<KnowledgeQueryProps> = ({ onQuery, isQuerying }) => {
  const [queryText, setQueryText] = useState('');
  const [topK, setTopK] = useState(5);
  const [scoreThreshold, setScoreThreshold] = useState(0.0);
  const [showOptions, setShowOptions] = useState(false);
  const [results, setResults] = useState<KnowledgeQueryResultItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryText.trim()) return;

    setError(null);
    try {
      const items = await onQuery(queryText.trim(), topK, scoreThreshold);
      setResults(items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to query knowledge base.';
      setError(msg);
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.7) return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30';
    if (score >= 0.4) return 'bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30';
    return 'bg-[var(--surface-elevated)] text-[var(--text-muted)] border-[var(--border)]';
  };

  return (
    <div className="bg-[var(--surface-elevated)] border border-[var(--border)] rounded-2xl sm:rounded-3xl p-5 sm:p-6 space-y-4 shadow-xs">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[var(--border)] pb-3.5">
        <div>
          <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[var(--color-purple)]" />
            <span>Test Knowledge Retrieval</span>
          </h2>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            Evaluate semantic grounding against your project documents and verify source citations.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowOptions(!showOptions)}
          className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] px-2.5 py-1.5 rounded-xl bg-[var(--surface)] border border-[var(--border)] transition-colors w-fit cursor-pointer"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          <span>{showOptions ? 'Hide Parameters' : 'Parameters'}</span>
        </button>
      </div>

      {/* Query Form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              placeholder="Ask something about this business (e.g. 'What is your refund policy?')..."
              className="w-full bg-[var(--surface)] border border-[var(--border)] rounded-xl pl-10 pr-4 py-2.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--color-purple)] focus:ring-1 focus:ring-[var(--color-purple)] transition-all"
              disabled={isQuerying}
            />
            <Search className="w-4 h-4 text-[var(--text-muted)] absolute left-3.5 top-3" />
          </div>
          <button
            type="submit"
            disabled={isQuerying || !queryText.trim()}
            className="px-5 py-2.5 bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 disabled:opacity-50 text-white rounded-xl text-xs font-semibold inline-flex items-center gap-2 shadow-xs transition-all shrink-0 cursor-pointer disabled:cursor-not-allowed"
          >
            {isQuerying ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Retrieving...
              </>
            ) : (
              <>
                <Search className="w-3.5 h-3.5" />
                Query
              </>
            )}
          </button>
        </div>

        {/* Collapsible Tuning Parameters */}
        {showOptions && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 bg-[var(--surface)]/70 border border-[var(--border)] rounded-2xl text-xs">
            <div className="space-y-1.5">
              <div className="flex justify-between text-[var(--text-secondary)]">
                <span>Top K Results:</span>
                <span className="font-mono text-[var(--text-primary)] font-semibold">{topK}</span>
              </div>
              <input
                type="range"
                min="1"
                max="20"
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="w-full accent-[var(--color-purple)] cursor-pointer"
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-[var(--text-secondary)]">
                <span>Score Threshold:</span>
                <span className="font-mono text-[var(--text-primary)] font-semibold">{scoreThreshold.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0.0"
                max="0.9"
                step="0.05"
                value={scoreThreshold}
                onChange={(e) => setScoreThreshold(Number(e.target.value))}
                className="w-full accent-[var(--color-purple)] cursor-pointer"
              />
            </div>
          </div>
        )}
      </form>

      {/* Error Message */}
      {error && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-2xl text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2 shadow-xs">
          <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Results Container */}
      {results && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-2">
            <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
              Ranked Grounding Results
            </h3>
            <span className="text-xs text-[var(--text-muted)] font-mono">
              {results.length} {results.length === 1 ? 'match' : 'matches'}
            </span>
          </div>

          {results.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)] italic text-center py-5">
              No matching knowledge chunks found above the score threshold.
            </p>
          ) : (
            <div className="space-y-3">
              {results.map((item, idx) => (
                <div
                  key={item.chunk_id || idx}
                  className="bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--color-purple)]/40 rounded-2xl p-4 space-y-2.5 transition-colors shadow-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded-lg bg-[var(--surface-elevated)] text-[var(--color-purple)] border border-[var(--border)]">
                        #{idx + 1}
                      </span>
                      <span className="flex items-center gap-1.5 font-medium text-[var(--text-primary)]">
                        <FileText className="w-3.5 h-3.5 text-[var(--color-purple)]" />
                        {item.document_filename}
                      </span>
                      {item.source_location && (
                        <span className="flex items-center gap-1 text-[11px] bg-purple-100/80 dark:bg-purple-950/60 border border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded-full font-medium">
                          <Bookmark className="w-3 h-3 text-[var(--color-purple)]" />
                          {item.source_location}
                        </span>
                      )}
                    </div>

                    <span
                      className={`font-mono text-[11px] px-2.5 py-0.5 rounded-full border font-semibold ${getScoreColor(
                        item.score
                      )}`}
                    >
                      Score: {(item.score * 100).toFixed(1)}%
                    </span>
                  </div>

                  <p className="text-xs text-[var(--text-secondary)] font-sans leading-relaxed bg-[var(--surface-elevated)] p-3.5 rounded-xl border border-[var(--border)]/70 whitespace-pre-wrap">
                    &quot;{item.text}&quot;
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
