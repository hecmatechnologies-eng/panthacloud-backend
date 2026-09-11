export type {
  DocumentStatus,
  KnowledgeBase,
  KnowledgeChunk,
  KnowledgeDocument,
  KnowledgeQueryRequest,
  KnowledgeQueryResponse,
  KnowledgeQueryResultItem,
} from '@/lib/api/knowledge';

import { KnowledgeDocument } from '@/lib/api/knowledge';

export interface UseKnowledgeBaseOptions {
  orgId?: string;
  projectId?: string;
  autoPoll?: boolean;
  onStatusChange?: (isCompleted: boolean) => void;
}

export interface KnowledgeStageOutput {
  projectId: string;
  readyDocumentCount: number;
  totalChunkCount: number;
  groundingReady: boolean;
  documents: KnowledgeDocument[];
}

export interface KnowledgeBaseViewProps {
  orgId?: string;
  projectId?: string;
}
