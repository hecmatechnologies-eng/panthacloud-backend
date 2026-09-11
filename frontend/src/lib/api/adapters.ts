import { fetchApi } from './client';

export type AdapterStatus =
  | 'PLANNED'
  | 'CONFIGURED'
  | 'READY'
  | 'DISABLED'
  | 'REVIEW_REQUIRED'
  | 'DEPRECATED';

export type AdapterType =
  | 'DATABASE'
  | 'CACHE'
  | 'PAYMENT'
  | 'STORAGE'
  | 'WEBHOOK'
  | 'MESSAGE_BROKER'
  | 'AUTHENTICATION'
  | 'EXTERNAL_SERVICE'
  | 'UNKNOWN';

export interface AdapterOperation {
  operation_id: string;
  operation_type: string;
  description?: string | null;
  target?: string | null;
  parameters: Record<string, unknown>;
  safety_classification: string;
  evidence?: Record<string, unknown> | Array<unknown> | null;
}

export interface AdapterConfiguration {
  environment_variables: string[];
  connection_parameters: Record<string, unknown>;
  options: Record<string, unknown>;
  evidence?: Record<string, unknown> | Array<unknown> | null;
}

export interface IntegrationAdapter {
  id: string;
  project_id: string;
  snapshot_id: string;
  integration_plan_id?: string | null;
  name: string;
  adapter_type: AdapterType;
  provider?: string | null;
  status: AdapterStatus;
  operations: AdapterOperation[];
  configuration: AdapterConfiguration;
  required_credentials: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export const integrationAdaptersApi = {
  async list(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    token?: string
  ): Promise<IntegrationAdapter[]> {
    return fetchApi<IntegrationAdapter[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/integration-adapters`,
      { token, cache: 'no-store' }
    );
  },

  async get(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    adapterId: string,
    token?: string
  ): Promise<IntegrationAdapter> {
    return fetchApi<IntegrationAdapter>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/integration-adapters/${adapterId}`,
      { token, cache: 'no-store' }
    );
  },

  async create(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    integrationPlanId?: string,
    token?: string
  ): Promise<IntegrationAdapter[]> {
    return fetchApi<IntegrationAdapter[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/integration-adapters`,
      {
        method: 'POST',
        body: JSON.stringify(integrationPlanId ? { integration_plan_id: integrationPlanId } : {}),
        token,
      }
    );
  },
};
