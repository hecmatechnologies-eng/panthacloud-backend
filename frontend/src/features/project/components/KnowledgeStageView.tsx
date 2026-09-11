'use client';

import React from 'react';
import { useProject } from '../context';
import { useKnowledgeBase } from '@/features/knowledge';
import { Project } from '@/lib/api';
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FileText,
  Layers,
  RefreshCw,
  Sparkles,
  Database,
  Cpu,
} from 'lucide-react';
import {
  DocumentUpload,
  DocumentList,
  DocumentDetails,
  KnowledgeQuery,
} from '@/features/knowledge';

export interface KnowledgeStageViewProps {
  project: Project;
  className?: string;
}

export const KnowledgeStageView: React.FC<KnowledgeStageViewProps> = ({
  project,
  className = '',
}) => {
  const { activeOrg, setActiveItem, markStageCompleted, isStageCompleted } = useProject();
  const orgId = project.organization_id || activeOrg?.id;

  const handleStatusChange = React.useCallback(
    (isCompleted: boolean) => {
      if (isStageCompleted('knowledge') !== isCompleted) {
        markStageCompleted('knowledge', isCompleted);
      }
    },
    [markStageCompleted, isStageCompleted]
  );

  const {
    documents,
    selectedDocument,
    isLoading,
    isUploading,
    isQuerying,
    error,
    isCompleted,
    knowledgeOutput,
    refresh,
    uploadDocument,
    deleteDocument,
    inspectDocument,
    closeInspect,
    queryKnowledge,
  } = useKnowledgeBase({
    orgId,
    projectId: project.id,
    autoPoll: true,
    onStatusChange: handleStatusChange,
  });

  return (
    <div
      data-testid="knowledge-stage-view"
      className={`flex-1 w-full max-w-4xl py-4 space-y-6 text-left transition-colors duration-150 ${className}`}
    >
      <div data-testid="stage-view-knowledge" className="hidden" aria-hidden="true" />
      {/* Back to Overview */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setActiveItem('overview')}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer group"
        >
          <ArrowLeft className="w-3.5 h-3.5 transition-transform group-hover:-translate-x-0.5" />
          <span>Back to Overview</span>
        </button>

        <button
          type="button"
          onClick={refresh}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[var(--surface-elevated)] hover:bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
          title="Refresh Documents"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-[var(--color-purple)]' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Stage Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold uppercase tracking-wider bg-purple-100/80 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border border-purple-200/60 dark:border-purple-900/40">
            BUILD · Stage 2 of 5
          </span>
          {isCompleted && (
            <span
              data-testid="knowledge-ready-badge"
              className="flex items-center gap-1 text-[11px] font-mono text-emerald-600 dark:text-emerald-400 font-medium"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Grounding Ready</span>
            </span>
          )}
        </div>

        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--text-primary)] transition-colors">
          Knowledge Base & Grounding
        </h2>

        <p className="text-xs sm:text-sm text-[var(--text-secondary)] transition-colors leading-relaxed max-w-2xl">
          Upload business documents, policies, FAQs, or manuals to give your assistant authoritative, grounded answers with citations.
        </p>
      </div>

      {/* Global Error Notice */}
      {error && (
        <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-2xl text-xs text-rose-600 dark:text-rose-400 flex items-center justify-between shadow-xs">
          <span>{error}</span>
          <button
            onClick={refresh}
            className="underline hover:text-rose-700 dark:hover:text-rose-300 font-semibold cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* Metrics Strip */}
      <div
        data-testid="knowledge-metrics-strip"
        className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs"
      >
        <div className="p-3.5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] shadow-xs space-y-1">
          <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider flex items-center gap-1.5">
            <FileText className="w-3 h-3 text-[var(--color-purple)]" />
            Documents
          </span>
          <p className="text-xs font-semibold text-[var(--text-primary)] font-mono">
            {documents.length} ({knowledgeOutput.readyDocumentCount} ready)
          </p>
        </div>

        <div className="p-3.5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] shadow-xs space-y-1">
          <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider flex items-center gap-1.5">
            <Layers className="w-3 h-3 text-[var(--color-purple)]" />
            Vector Chunks
          </span>
          <p className="text-xs font-semibold text-[var(--text-primary)] font-mono">
            {knowledgeOutput.totalChunkCount} chunks
          </p>
        </div>

        <div className="p-3.5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] shadow-xs space-y-1">
          <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider flex items-center gap-1.5">
            <Cpu className="w-3 h-3 text-[var(--color-purple)]" />
            Embeddings
          </span>
          <p className="text-xs font-semibold text-[var(--text-primary)] font-mono">
            384-dim (Cosine)
          </p>
        </div>

        <div className="p-3.5 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] shadow-xs space-y-1">
          <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] tracking-wider flex items-center gap-1.5">
            <Database className="w-3 h-3 text-[var(--color-purple)]" />
            Grounding Status
          </span>
          <p className={`text-xs font-semibold flex items-center gap-1 font-mono ${
            isCompleted
              ? 'text-emerald-600 dark:text-emerald-400'
              : 'text-[var(--text-muted)]'
          }`}>
            {isCompleted ? (
              <>
                <CheckCircle2 className="w-3 h-3" />
                <span>Verified Active</span>
              </>
            ) : (
              <span>Awaiting Ingestion</span>
            )}
          </p>
        </div>
      </div>

      {/* Completion Banner when Ready */}
      {isCompleted && (
        <div
          data-testid="knowledge-completion-banner"
          className="p-5 rounded-3xl bg-purple-50/70 dark:bg-purple-950/20 border border-purple-200/70 dark:border-purple-900/40 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-xs"
        >
          <div className="space-y-1">
            <div className="text-xs font-bold text-purple-700 dark:text-purple-300 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Next Recommended Stage: Assistant Configuration</span>
            </div>
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
              {knowledgeOutput.readyDocumentCount} document{knowledgeOutput.readyDocumentCount === 1 ? '' : 's'} indexed into {knowledgeOutput.totalChunkCount} vector chunks. Your assistant can now be tailored with identity, prompt instructions, and behavior.
            </p>
          </div>

          <button
            type="button"
            data-testid="advance-to-assistant"
            onClick={() => setActiveItem('assistant')}
            className="px-4 py-2.5 rounded-xl bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white text-xs font-medium shadow-xs transition-all cursor-pointer flex items-center justify-center gap-1.5 shrink-0"
          >
            <span>Configure Assistant</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Pillar 1: Upload Source */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-[var(--color-purple)]" />
            <span>Upload Knowledge Sources</span>
          </h3>
        </div>
        <DocumentUpload onUpload={uploadDocument} isUploading={isUploading} />
      </div>

      {/* Pillar 2: Document Library */}
      <div className="space-y-3">
        <DocumentList
          documents={documents}
          isLoading={isLoading}
          onInspect={inspectDocument}
          onDelete={deleteDocument}
        />
      </div>

      {/* Pillar 3: Grounding Bench */}
      <div className="space-y-3">
        <KnowledgeQuery onQuery={queryKnowledge} isQuerying={isQuerying} />
      </div>

      {/* Inspect Modal Drawer */}
      <DocumentDetails document={selectedDocument} onClose={closeInspect} />
    </div>
  );
};
