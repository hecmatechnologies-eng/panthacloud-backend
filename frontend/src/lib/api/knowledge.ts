import { fetchApi } from './client';

export type DocumentStatus = 'PENDING' | 'PROCESSING' | 'READY' | 'FAILED';

export interface KnowledgeChunk {
  id: string;
  chunk_index: number;
  text: string;
  page_number?: number | null;
  source_location?: string | null;
  token_count: number;
  created_at: string;
}

export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  filename: string;
  content_type: string;
  file_size_bytes: number;
  status: DocumentStatus;
  error_message?: string | null;
  chunks_count: number;
  created_at: string;
  updated_at: string;
  chunks?: KnowledgeChunk[];
}

export interface KnowledgeBase {
  id: string;
  project_id: string;
  name: string;
  description?: string | null;
  documents_count?: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeQueryResultItem {
  chunk_id: string;
  document_id: string;
  document_filename: string;
  chunk_index: number;
  page_number?: number | null;
  source_location?: string | null;
  text: string;
  score: number;
}

export interface KnowledgeQueryRequest {
  query: string;
  top_k?: number;
  score_threshold?: number;
}

export interface KnowledgeQueryResponse {
  query: string;
  total_matches: number;
  results: KnowledgeQueryResultItem[];
}

export const knowledgeApi = {
  listDocuments: async (orgId: string, projectId: string): Promise<KnowledgeDocument[]> => {
    return fetchApi<KnowledgeDocument[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/knowledge/documents`
    );
  },

  getDocument: async (
    orgId: string,
    projectId: string,
    documentId: string
  ): Promise<KnowledgeDocument> => {
    return fetchApi<KnowledgeDocument>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/knowledge/documents/${documentId}`
    );
  },

  uploadDocument: async (
    orgId: string,
    projectId: string,
    file: File
  ): Promise<KnowledgeDocument> => {
    const formData = new FormData();
    formData.append('file', file);

    return fetchApi<KnowledgeDocument>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/knowledge/documents`,
      {
        method: 'POST',
        body: formData,
      }
    );
  },

  deleteDocument: async (
    orgId: string,
    projectId: string,
    documentId: string
  ): Promise<void> => {
    return fetchApi<void>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/knowledge/documents/${documentId}`,
      {
        method: 'DELETE',
      }
    );
  },

  queryKnowledge: async (
    orgId: string,
    projectId: string,
    request: KnowledgeQueryRequest
  ): Promise<KnowledgeQueryResponse> => {
    return fetchApi<KnowledgeQueryResponse>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/knowledge/query`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    );
  },
};
