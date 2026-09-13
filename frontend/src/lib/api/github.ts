import { fetchApi } from './client';

export interface GitHubInstallUrlRead {
  url: string;
}

export interface GitHubInstallationRead {
  id: string;
  installation_id: number;
  account_login: string;
  account_type: string;
  repository_selection: string;
}

export interface GitHubRepositoryRead {
  full_name: string;
  name: string;
  owner: string | null;
  private: boolean;
  default_branch: string;
  installation_id: number;
}

export interface GitHubRepositoryList {
  total_count: number;
  repositories: GitHubRepositoryRead[];
  page: number;
  per_page: number;
}

export const githubApi = {
  installUrl: async (orgId: string, token?: string): Promise<GitHubInstallUrlRead> =>
    fetchApi<GitHubInstallUrlRead>(`/api/v1/organizations/${orgId}/github/install-url`, {
      token,
      cache: 'no-store',
    }),

  installations: async (orgId: string, token?: string): Promise<GitHubInstallationRead[]> =>
    fetchApi<GitHubInstallationRead[]>(`/api/v1/organizations/${orgId}/github/installations`, {
      token,
      cache: 'no-store',
    }),

  repositories: async (
    orgId: string,
    token?: string,
    page = 1,
    perPage = 30
  ): Promise<GitHubRepositoryList> =>
    fetchApi<GitHubRepositoryList>(
      `/api/v1/organizations/${orgId}/github/repositories?page=${page}&per_page=${perPage}`,
      { token, cache: 'no-store' }
    ),
};
