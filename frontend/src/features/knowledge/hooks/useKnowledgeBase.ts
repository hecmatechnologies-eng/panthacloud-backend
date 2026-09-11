'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  KnowledgeDocument,
  KnowledgeQueryResultItem,
  KnowledgeStageOutput,
  UseKnowledgeBaseOptions,
} from '../types';
import { knowledgeApi } from '@/lib/api/knowledge';

export function useKnowledgeBase({
  orgId,
  projectId,
  autoPoll = false,
  onStatusChange,
}: UseKnowledgeBaseOptions) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<KnowledgeDocument | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isQuerying, setIsQuerying] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  // Track last reported status to avoid duplicate updates and eliminate loop feedback
  const lastStatusRef = useRef<boolean | null>(null);

  const notifyStatus = useCallback((ready: boolean) => {
    if (lastStatusRef.current !== ready) {
      lastStatusRef.current = ready;
      onStatusChangeRef.current?.(ready);
    }
  }, []);

  const loadDocuments = useCallback(async () => {
    if (!orgId || !projectId) return;

    setIsLoading(true);
    setError(null);
    try {
      const data = await knowledgeApi.listDocuments(orgId, projectId);
      const docs = data || [];
      setDocuments(docs);
      const isReady = docs.some((d) => d.status === 'READY');
      notifyStatus(isReady);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch knowledge documents.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [orgId, projectId, notifyStatus]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Optional auto-polling for documents still in PROCESSING status
  useEffect(() => {
    if (!autoPoll || !orgId || !projectId) return;
    const hasProcessing = documents.some((d) => d.status === 'PROCESSING' || d.status === 'PENDING');
    if (!hasProcessing) return;

    const interval = setInterval(() => {
      loadDocuments();
    }, 3000);

    return () => clearInterval(interval);
  }, [autoPoll, documents, loadDocuments, orgId, projectId]);

  const uploadDocument = async (file: File): Promise<KnowledgeDocument> => {
    if (!orgId || !projectId) {
      throw new Error('Organization or Project context is missing.');
    }

    setIsUploading(true);
    setError(null);
    try {
      const newDoc = await knowledgeApi.uploadDocument(orgId, projectId, file);
      setDocuments((prev) => {
        const next = [newDoc, ...prev.filter((d) => d.id !== newDoc.id)];
        const isReady = next.some((d) => d.status === 'READY');
        notifyStatus(isReady);
        return next;
      });
      return newDoc;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload failed.';
      setError(msg);
      throw err;
    } finally {
      setIsUploading(false);
    }
  };

  const deleteDocument = async (docId: string): Promise<void> => {
    if (!orgId || !projectId) {
      throw new Error('Organization or Project context is missing.');
    }

    setError(null);
    try {
      await knowledgeApi.deleteDocument(orgId, projectId, docId);
      setDocuments((prev) => {
        const next = prev.filter((d) => d.id !== docId);
        const isReady = next.some((d) => d.status === 'READY');
        notifyStatus(isReady);
        return next;
      });
      if (selectedDocument?.id === docId) {
        setSelectedDocument(null);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Delete failed.';
      setError(msg);
      throw err;
    }
  };

  const inspectDocument = async (doc: KnowledgeDocument): Promise<void> => {
    if (!orgId || !projectId) return;

    // Load full details including chunks
    try {
      const fullDoc = await knowledgeApi.getDocument(orgId, projectId, doc.id);
      setSelectedDocument(fullDoc);
    } catch {
      // Fallback to the passed doc if full fetch fails
      setSelectedDocument(doc);
    }
  };

  const closeInspect = () => {
    setSelectedDocument(null);
  };

  const queryKnowledge = async (
    query: string,
    topK: number = 5,
    scoreThreshold: number = 0.0
  ): Promise<KnowledgeQueryResultItem[]> => {
    if (!orgId || !projectId) {
      throw new Error('Organization or Project context is missing.');
    }

    setIsQuerying(true);
    setError(null);
    try {
      const resp = await knowledgeApi.queryKnowledge(orgId, projectId, {
        query,
        top_k: topK,
        score_threshold: scoreThreshold,
      });
      return resp.results || [];
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Query failed.';
      setError(msg);
      throw err;
    } finally {
      setIsQuerying(false);
    }
  };

  const readyDocumentCount = documents.filter((d) => d.status === 'READY').length;
  const totalChunkCount = documents.reduce((sum, d) => sum + (d.chunks_count || 0), 0);
  const groundingReady = readyDocumentCount > 0;

  const knowledgeOutput: KnowledgeStageOutput = {
    projectId: projectId || '',
    readyDocumentCount,
    totalChunkCount,
    groundingReady,
    documents,
  };

  return {
    documents,
    selectedDocument,
    isLoading,
    isUploading,
    isQuerying,
    error,
    isCompleted: groundingReady,
    knowledgeOutput,
    refresh: loadDocuments,
    uploadDocument,
    deleteDocument,
    inspectDocument,
    closeInspect,
    queryKnowledge,
  };
}
