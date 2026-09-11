import { fetchApi } from './client';

export type RepositoryProvider = 'github' | 'gitlab';
export type RepositoryStatus = 'PENDING' | 'CONNECTED' | 'DISCONNECTED' | 'ERROR';

export interface Repository {
  id: string;
  project_id: string;
  integration_id: string;
  provider: RepositoryProvider;
  name: string;
  full_name: string;
  external_id: string;
  default_branch: string;
  url?: string | null;
  status: RepositoryStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CreateRepositoryInput {
  integration_id: string;
  provider: RepositoryProvider;
  name: string;
  full_name: string;
  external_id: string;
  default_branch?: string;
  url?: string;
  status?: RepositoryStatus;
  metadata?: Record<string, unknown>;
}

export const repositoriesApi = {
  async list(orgId: string, projectId: string, token?: string): Promise<Repository[]> {
    return fetchApi<Repository[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories`,
      { token, cache: 'no-store' }
    );
  },

  async get(
    orgId: string,
    projectId: string,
    repositoryId: string,
    token?: string
  ): Promise<Repository> {
    return fetchApi<Repository>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}`,
      { token, cache: 'no-store' }
    );
  },

  async create(
    orgId: string,
    projectId: string,
    data: CreateRepositoryInput,
    token?: string
  ): Promise<Repository> {
    return fetchApi<Repository>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories`,
      {
        method: 'POST',
        body: JSON.stringify(data),
        token,
      }
    );
  },

  async delete(
    orgId: string,
    projectId: string,
    repositoryId: string,
    token?: string
  ): Promise<void> {
    return fetchApi<void>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}`,
      { method: 'DELETE', token }
    );
  },
};
