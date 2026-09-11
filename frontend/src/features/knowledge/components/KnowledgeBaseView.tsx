'use client';

import React from 'react';
import { BookOpen, RefreshCw } from 'lucide-react';
import { KnowledgeBaseViewProps } from '../types';
import { useKnowledgeBase } from '../hooks/useKnowledgeBase';
import { DocumentUpload } from './DocumentUpload';
import { DocumentList } from './DocumentList';
import { DocumentDetails } from './DocumentDetails';
import { KnowledgeQuery } from './KnowledgeQuery';

export const KnowledgeBaseView: React.FC<KnowledgeBaseViewProps> = ({
  orgId,
  projectId,
}) => {
  const {
    documents,
    selectedDocument,
    isLoading,
    isUploading,
    isQuerying,
    error,
    refresh,
    uploadDocument,
    deleteDocument,
    inspectDocument,
    closeInspect,
    queryKnowledge,
  } = useKnowledgeBase({ orgId, projectId, autoPoll: true });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-sky-400" />
            <h1 className="text-lg font-bold text-white tracking-tight">
              Knowledge Base
            </h1>
            <span className="text-[10px] font-mono uppercase bg-sky-950/80 border border-sky-800 text-sky-300 px-2 py-0.5 rounded font-semibold">
              Grounding Engine
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            Business knowledge that grounds your website assistant with verified, citable answers.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-medium transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-sky-400' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Global Error Notice */}
      {error && (
        <div className="p-3 bg-red-950/30 border border-red-800/80 rounded-xl text-xs text-red-300 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={refresh} className="underline hover:text-white font-semibold">
            Retry
          </button>
        </div>
      )}

      {/* Document Upload Section */}
      <DocumentUpload onUpload={uploadDocument} isUploading={isUploading} />

      {/* Documents Table / List */}
      <DocumentList
        documents={documents}
        isLoading={isLoading}
        onInspect={inspectDocument}
        onDelete={deleteDocument}
      />

      {/* Semantic Retrieval Test Tool */}
      <KnowledgeQuery onQuery={queryKnowledge} isQuerying={isQuerying} />

      {/* Document Details Modal / Drawer */}
      <DocumentDetails document={selectedDocument} onClose={closeInspect} />
    </div>
  );
};
