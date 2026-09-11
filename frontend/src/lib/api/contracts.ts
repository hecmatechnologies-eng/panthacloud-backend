import { fetchApi } from './client';

export type ContractStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
export type ContractSource = 'OPENAPI' | 'SWAGGER' | 'STATIC_ROUTE' | 'DISCOVERY';

export interface AuthenticationScheme {
  name: string;
  type: string;
  scheme?: string | null;
  bearer_format?: string | null;
  in?: string | null;
  description?: string | null;
  flows?: Record<string, unknown> | null;
}

export interface ReconciliationFinding {
  path: string;
  method: string;
  category: 'MATCHED' | 'DOCUMENTED_ONLY' | 'IMPLEMENTED_ONLY' | 'CONFLICT';
  details?: string | null;
  contract_operation_id?: string | null;
  source_file?: string | null;
  source_line?: number | null;
}

export interface ContractReconciliation {
  matched_count: number;
  documented_only_count: number;
  implemented_only_count: number;
  conflict_count: number;
  findings: ReconciliationFinding[];
}

export interface ApiOperation {
  id: string;
  contract_id: string;
  method: string;
  path: string;
  operation_id?: string | null;
  summary?: string | null;
  description?: string | null;
  source: ContractSource;
  source_file?: string | null;
  source_line?: number | null;
  authentication_required: boolean;
  request_schema?: Record<string, unknown> | null;
  response_schema?: Record<string, unknown> | null;
  tags: string[];
  evidence: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ApiContract {
  id: string;
  snapshot_id: string;
  discovery_run_id: string;
  status: ContractStatus;
  title: string;
  version: string;
  format: string;
  servers: Array<{ url: string; description?: string }>;
  authentication: AuthenticationScheme[];
  schemas: Record<string, unknown>;
  reconciliation: ContractReconciliation;
  metadata: Record<string, unknown>;
  operations: ApiOperation[];
  created_at: string;
  updated_at: string;
}

export const contractsApi = {
  async list(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    token?: string
  ): Promise<ApiContract[]> {
    return fetchApi<ApiContract[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/contracts`,
      { token, cache: 'no-store' }
    );
  },

  async get(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    contractId: string,
    token?: string
  ): Promise<ApiContract> {
    return fetchApi<ApiContract>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/contracts/${contractId}`,
      { token, cache: 'no-store' }
    );
  },

  async create(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    discoveryRunId?: string,
    token?: string
  ): Promise<ApiContract> {
    return fetchApi<ApiContract>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/contracts`,
      {
        method: 'POST',
        body: JSON.stringify(discoveryRunId ? { discovery_run_id: discoveryRunId } : {}),
        token,
      }
    );
  },
};
