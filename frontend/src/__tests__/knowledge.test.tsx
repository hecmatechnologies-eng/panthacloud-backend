import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  KnowledgeBaseView,
  DocumentUpload,
  DocumentList,
  DocumentStatusBadge,
  DocumentDetails,
  KnowledgeQuery,
  ChunkPreview,
} from '@/features/knowledge';
import { KnowledgeDocument, KnowledgeChunk } from '@/features/knowledge/types';
import { knowledgeApi } from '@/lib/api/knowledge';

// Mock knowledgeApi
vi.mock('@/lib/api/knowledge', () => ({
  knowledgeApi: {
    listDocuments: vi.fn(),
    getDocument: vi.fn(),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    queryKnowledge: vi.fn(),
  },
}));

const mockChunks: KnowledgeChunk[] = [
  {
    id: 'chunk-1',
    chunk_index: 0,
    text: 'Customers may request a full refund within thirty days of delivery.',
    page_number: null,
    source_location: 'Heading: Refund Policy',
    token_count: 12,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'chunk-2',
    chunk_index: 1,
    text: 'Standard shipping takes 3-5 business days across the country.',
    page_number: 2,
    source_location: 'Page 2',
    token_count: 9,
    created_at: '2026-01-01T00:00:00Z',
  },
];

const mockDocuments: KnowledgeDocument[] = [
  {
    id: 'doc-1',
    knowledge_base_id: 'kb-1',
    filename: 'shipping_policy.md',
    content_type: 'text/markdown',
    file_size_bytes: 4200,
    status: 'READY',
    error_message: null,
    chunks_count: 2,
    created_at: '2026-01-01T10:00:00Z',
    updated_at: '2026-01-01T10:00:00Z',
    chunks: mockChunks,
  },
  {
    id: 'doc-2',
    knowledge_base_id: 'kb-1',
    filename: 'annual_report.pdf',
    content_type: 'application/pdf',
    file_size_bytes: 524288,
    status: 'PROCESSING',
    error_message: null,
    chunks_count: 0,
    created_at: '2026-01-01T11:00:00Z',
    updated_at: '2026-01-01T11:00:00Z',
    chunks: [],
  },
  {
    id: 'doc-3',
    knowledge_base_id: 'kb-1',
    filename: 'corrupted_file.txt',
    content_type: 'text/plain',
    file_size_bytes: 120,
    status: 'FAILED',
    error_message: 'Processing failed: Document contains no extractable text content.',
    chunks_count: 0,
    created_at: '2026-01-01T12:00:00Z',
    updated_at: '2026-01-01T12:00:00Z',
    chunks: [],
  },
];

describe('Knowledge Feature Component Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('DocumentStatusBadge', () => {
    it('renders correct styling and text for each status', () => {
      const { rerender } = render(<DocumentStatusBadge status="READY" />);
      expect(screen.getByText('READY')).toBeDefined();

      rerender(<DocumentStatusBadge status="PROCESSING" />);
      expect(screen.getByText('PROCESSING')).toBeDefined();

      rerender(<DocumentStatusBadge status="PENDING" />);
      expect(screen.getByText('PENDING')).toBeDefined();

      rerender(<DocumentStatusBadge status="FAILED" />);
      expect(screen.getByText('FAILED')).toBeDefined();
    });
  });

  describe('ChunkPreview', () => {
    it('renders chunk index, heading citation, and text excerpt', () => {
      render(<ChunkPreview chunk={mockChunks[0]} />);

      expect(screen.getByText('Chunk 1')).toBeDefined();
      expect(screen.getByText('Heading: Refund Policy')).toBeDefined();
      expect(screen.getByText(/Customers may request a full refund/i)).toBeDefined();
    });

    it('renders page number citation for PDF chunk', () => {
      render(<ChunkPreview chunk={mockChunks[1]} />);

      expect(screen.getByText('Chunk 2')).toBeDefined();
      expect(screen.getByText('Page 2')).toBeDefined();
      expect(screen.getByText(/Standard shipping takes 3-5/i)).toBeDefined();
    });
  });

  describe('DocumentUpload', () => {
    it('rejects unsupported extensions with client error', async () => {
      const onUpload = vi.fn();
      render(<DocumentUpload onUpload={onUpload} isUploading={false} />);

      const file = new File(['binary'], 'installer.exe', { type: 'application/x-msdownload' });
      const input = document.getElementById('knowledge-file-input') as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Unsupported format '\.exe'/i)).toBeDefined();
      });
      expect(onUpload).not.toHaveBeenCalled();
    });

    it('rejects files larger than 10 MB', async () => {
      const onUpload = vi.fn();
      render(<DocumentUpload onUpload={onUpload} isUploading={false} />);

      // 11 MB file
      const bigFile = new File(['a'.repeat(11 * 1024 * 1024)], 'huge.pdf', { type: 'application/pdf' });
      Object.defineProperty(bigFile, 'size', { value: 11 * 1024 * 1024 });

      const input = document.getElementById('knowledge-file-input') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [bigFile] } });

      await waitFor(() => {
        expect(screen.getByText(/exceeds the maximum limit of 10 MB/i)).toBeDefined();
      });
      expect(onUpload).not.toHaveBeenCalled();
    });

    it('calls onUpload with valid file', async () => {
      const onUpload = vi.fn().mockResolvedValue(undefined);
      render(<DocumentUpload onUpload={onUpload} isUploading={false} />);

      const file = new File(['# Terms'], 'terms.md', { type: 'text/markdown' });
      const input = document.getElementById('knowledge-file-input') as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(onUpload).toHaveBeenCalledWith(file);
      });
    });
  });

  describe('DocumentList', () => {
    it('renders empty state when documents array is empty', () => {
      render(
        <DocumentList
          documents={[]}
          isLoading={false}
          onInspect={vi.fn()}
          onDelete={vi.fn()}
        />
      );

      expect(screen.getByText('No knowledge documents yet')).toBeDefined();
    });

    it('renders table rows for documents with status badges and inspect button', () => {
      const onInspect = vi.fn();
      render(
        <DocumentList
          documents={mockDocuments}
          isLoading={false}
          onInspect={onInspect}
          onDelete={vi.fn()}
        />
      );

      expect(screen.getByText('shipping_policy.md')).toBeDefined();
      expect(screen.getByText('annual_report.pdf')).toBeDefined();
      expect(screen.getByText('corrupted_file.txt')).toBeDefined();
      expect(screen.getByText('READY')).toBeDefined();
      expect(screen.getByText('PROCESSING')).toBeDefined();
      expect(screen.getByText('FAILED')).toBeDefined();

      const inspectBtns = screen.getAllByText('Inspect');
      fireEvent.click(inspectBtns[0]);
      expect(onInspect).toHaveBeenCalledWith(mockDocuments[0]);
    });

    it('handles delete action with confirmation', async () => {
      const onDelete = vi.fn().mockResolvedValue(undefined);
      vi.spyOn(window, 'confirm').mockReturnValue(true);

      render(
        <DocumentList
          documents={mockDocuments}
          isLoading={false}
          onInspect={vi.fn()}
          onDelete={onDelete}
        />
      );

      const deleteBtn = screen.getByLabelText('Delete shipping_policy.md');
      fireEvent.click(deleteBtn);

      expect(window.confirm).toHaveBeenCalled();
      await waitFor(() => {
        expect(onDelete).toHaveBeenCalledWith('doc-1');
      });
    });
  });

  describe('DocumentDetails Modal', () => {
    it('renders document metadata and chunks list, and triggers close', () => {
      const onClose = vi.fn();
      render(<DocumentDetails document={mockDocuments[0]} onClose={onClose} />);

      expect(screen.getByText('shipping_policy.md')).toBeDefined();
      expect(screen.getByText('Extracted Chunks & Citations')).toBeDefined();
      expect(screen.getByText('Heading: Refund Policy')).toBeDefined();
      expect(screen.getByText('Page 2')).toBeDefined();

      const closeBtn = screen.getByRole('button', { name: 'Close' });
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalled();
    });

    it('renders error message for failed document', () => {
      render(<DocumentDetails document={mockDocuments[2]} onClose={vi.fn()} />);

      expect(screen.getByText('corrupted_file.txt')).toBeDefined();
      expect(screen.getByText(/Document contains no extractable text content/i)).toBeDefined();
    });
  });

  describe('KnowledgeQuery Tool', () => {
    it('submits query and renders ranked results with scores and citations', async () => {
      const onQuery = vi.fn().mockResolvedValue([
        {
          chunk_id: 'chunk-1',
          document_id: 'doc-1',
          document_filename: 'shipping_policy.md',
          chunk_index: 0,
          page_number: null,
          source_location: 'Heading: Refund Policy',
          text: 'Customers may request a full refund within thirty days.',
          score: 0.88,
        },
      ]);

      render(<KnowledgeQuery onQuery={onQuery} isQuerying={false} />);

      const input = screen.getByPlaceholderText(/Ask something about this business/i);
      fireEvent.change(input, { target: { value: 'How to get a refund?' } });

      const submitBtn = screen.getByRole('button', { name: /Query/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(onQuery).toHaveBeenCalledWith('How to get a refund?', 5, 0.0);
      });

      await waitFor(() => {
        expect(screen.getByText('#1')).toBeDefined();
        expect(screen.getByText('Score: 88.0%')).toBeDefined();
        expect(screen.getByText('Heading: Refund Policy')).toBeDefined();
        expect(screen.getByText(/"Customers may request a full refund within thirty days\."/i)).toBeDefined();
      });
    });
  });

  describe('KnowledgeBaseView Integration', () => {
    it('fetches and displays documents from knowledgeApi on mount', async () => {
      vi.mocked(knowledgeApi.listDocuments).mockResolvedValue(mockDocuments);

      render(<KnowledgeBaseView orgId="org-1" projectId="proj-1" />);

      expect(screen.getByText('Knowledge Base')).toBeDefined();
      expect(screen.getByText('Grounding Engine')).toBeDefined();

      await waitFor(() => {
        expect(knowledgeApi.listDocuments).toHaveBeenCalledWith('org-1', 'proj-1');
        expect(screen.getByText('shipping_policy.md')).toBeDefined();
      });
    });
  });
});
