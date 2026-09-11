import { fetchApi } from './client';

export type SnapshotStatus = 'PENDING' | 'ACQUIRING' | 'READY' | 'FAILED' | 'EXPIRED' | 'DELETED';

export interface RepositorySnapshot {
  id: string;
  repository_id: string;
  branch: string;
  commit_sha?: string | null;
  status: SnapshotStatus;
  acquired_at?: string | null;
  completed_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CreateSnapshotInput {
  branch?: string;
}

export interface InspectionResult {
  snapshot_id: string;
  commit_sha: string;
  repository: {
    name: string;
    default_branch: string;
  };
  structure: {
    file_count: number;
    directory_count: number;
    total_size_bytes: number;
    maximum_depth: number;
  };
  languages: string[];
  frameworks: string[];
  manifests: string[];
  api_contracts: string[];
  deployment_files: string[];
}

export const snapshotsApi = {
  async list(
    orgId: string,
    projectId: string,
    repositoryId: string,
    token?: string
  ): Promise<RepositorySnapshot[]> {
    return fetchApi<RepositorySnapshot[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots`,
      { token, cache: 'no-store' }
    );
  },

  async get(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    token?: string
  ): Promise<RepositorySnapshot> {
    return fetchApi<RepositorySnapshot>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}`,
      { token, cache: 'no-store' }
    );
  },

  async create(
    orgId: string,
    projectId: string,
    repositoryId: string,
    data: CreateSnapshotInput,
    token?: string
  ): Promise<RepositorySnapshot> {
    return fetchApi<RepositorySnapshot>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots`,
      {
        method: 'POST',
        body: JSON.stringify(data),
        token,
      }
    );
  },

  async inspect(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    token?: string
  ): Promise<InspectionResult> {
    return fetchApi<InspectionResult>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/inspect`,
      {
        method: 'POST',
        token,
      }
    );
  },
};
