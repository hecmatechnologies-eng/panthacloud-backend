import { fetchApi } from './client';

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export const organizationsApi = {
  async list(token?: string): Promise<Organization[]> {
    return fetchApi<Organization[]>('/api/v1/organizations', {
      method: 'GET',
      token,
      cache: 'no-store',
    });
  },

  async get(orgId: string, token?: string): Promise<Organization> {
    return fetchApi<Organization>(`/api/v1/organizations/${orgId}`, {
      method: 'GET',
      token,
    });
  },
};
