'use client';

import React, { useRef, useState } from 'react';
import { AlertCircle, FileUp, Loader2, UploadCloud } from 'lucide-react';

interface DocumentUploadProps {
  onUpload: (file: File) => Promise<unknown>;
  isUploading: boolean;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const ALLOWED_EXTENSIONS = ['.pdf', '.md', '.markdown', '.txt'];

export const DocumentUpload: React.FC<DocumentUploadProps> = ({ onUpload, isUploading }) => {
  const [dragActive, setDragActive] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateAndUpload = async (file: File) => {
    setClientError(null);

    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setClientError(
        `Unsupported format '${ext}'. Only PDF, Markdown (.md), and Plain Text (.txt) are allowed.`
      );
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      setClientError(
        `File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds the maximum limit of 10 MB.`
      );
      return;
    }

    if (file.size === 0) {
      setClientError('Uploaded file is empty.');
      return;
    }

    try {
      await onUpload(file);
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to upload document.';
      setClientError(msg);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await validateAndUpload(e.dataTransfer.files[0]);
    }
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      await validateAndUpload(e.target.files[0]);
    }
  };

  return (
    <div className="space-y-3">
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-3xl p-7 sm:p-8 text-center transition-colors ${
          dragActive
            ? 'border-[var(--color-purple)] bg-[var(--color-purple)]/10'
            : 'border-[var(--border)] hover:border-[var(--color-purple)]/40 bg-[var(--surface-elevated)]/40'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.md,.markdown,.txt"
          onChange={handleChange}
          className="hidden"
          id="knowledge-file-input"
          disabled={isUploading}
        />

        <div className="w-12 h-12 rounded-2xl bg-purple-100/70 dark:bg-purple-950/60 border border-purple-200/80 dark:border-purple-900/50 flex items-center justify-center mx-auto text-[var(--color-purple)] mb-3 shadow-xs">
          {isUploading ? (
            <Loader2 className="w-6 h-6 animate-spin" />
          ) : (
            <UploadCloud className="w-6 h-6" />
          )}
        </div>

        <div className="space-y-1">
          <p className="text-sm font-semibold text-[var(--text-primary)] transition-colors">
            {isUploading ? 'Ingesting & Chunking Document...' : 'Upload business knowledge documents'}
          </p>
          <p className="text-xs text-[var(--text-secondary)] transition-colors max-w-md mx-auto leading-relaxed">
            Drag and drop or select a file. Supported formats:{' '}
            <span className="text-[var(--text-primary)] font-medium">PDF, Markdown (.md), and Plain Text (.txt)</span>.
            Max 10 MB.
          </p>
        </div>

        <div className="pt-3">
          <label
            htmlFor="knowledge-file-input"
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer transition-all shadow-xs ${
              isUploading
                ? 'bg-[var(--surface)] text-[var(--text-muted)] cursor-not-allowed border border-[var(--border)]'
                : 'bg-[var(--color-purple)] hover:bg-[var(--color-purple)]/90 text-white shadow-purple-950/20'
            }`}
          >
            <FileUp className="w-4 h-4" />
            {isUploading ? 'Processing Document...' : 'Select Document'}
          </label>
        </div>
      </div>

      {clientError && (
        <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-2xl text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2 shadow-xs">
          <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold">Upload Error:</span> {clientError}
          </div>
          <button
            onClick={() => setClientError(null)}
            className="text-rose-500 hover:text-rose-700 dark:hover:text-rose-300 text-xs font-bold cursor-pointer"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
};
