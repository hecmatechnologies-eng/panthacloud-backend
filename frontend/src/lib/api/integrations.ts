import { fetchApi } from './client';

export type IntegrationProvider = 'github' | 'gitlab' | 'external_api' | 'webhook';
export type IntegrationStatus = 'PENDING' | 'ACTIVE' | 'DISCONNECTED' | 'ERROR' | 'DISABLED';

export interface Integration {
  id: string;
  project_id: string;
  provider: IntegrationProvider;
  name: string;
  status: IntegrationStatus;
  configuration: Record<string, unknown>;
  has_credentials: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateIntegrationInput {
  name: string;
  provider: IntegrationProvider;
  configuration?: Record<string, unknown>;
  secrets?: Record<string, string>;
  status?: IntegrationStatus;
}

export const integrationsApi = {
  async list(orgId: string, projectId: string, token?: string): Promise<Integration[]> {
    return fetchApi<Integration[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/integrations`,
      { token, cache: 'no-store' }
    );
  },

  async create(
    orgId: string,
    projectId: string,
    data: CreateIntegrationInput,
    token?: string
  ): Promise<Integration> {
    return fetchApi<Integration>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/integrations`,
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
    integrationId: string,
    token?: string
  ): Promise<void> {
    return fetchApi<void>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/integrations/${integrationId}`,
      { method: 'DELETE', token }
    );
  },
};
