import { fetchApi } from './client';

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateProjectInput {
  name: string;
  slug?: string;
  description?: string;
}

export const projectsApi = {
  async list(orgId: string, token?: string): Promise<Project[]> {
    return fetchApi<Project[]>(`/api/v1/organizations/${orgId}/projects`, {
      method: 'GET',
      token,
      cache: 'no-store',
    });
  },

  async get(orgId: string, projectId: string, token?: string): Promise<Project> {
    return fetchApi<Project>(`/api/v1/organizations/${orgId}/projects/${projectId}`, {
      method: 'GET',
      token,
    });
  },

  async create(orgId: string, data: CreateProjectInput, token?: string): Promise<Project> {
    return fetchApi<Project>(`/api/v1/organizations/${orgId}/projects`, {
      method: 'POST',
      body: JSON.stringify(data),
      token,
    });
  },

  async delete(orgId: string, projectId: string, token?: string): Promise<void> {
    return fetchApi<void>(`/api/v1/organizations/${orgId}/projects/${projectId}`, {
      method: 'DELETE',
      token,
    });
  },
};
