import { fetchApi } from './client';

export type DiscoveryStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export interface Evidence {
  file: string;
  reason: string;
  line?: number | null;
  symbol?: string | null;
}

export interface FrameworkFinding {
  name: string;
  version?: string | null;
  evidence: Evidence[];
}

export interface EntrypointFinding {
  path: string;
  symbol: string;
  framework: string;
  type: string;
  evidence: Evidence[];
}

export interface RouteFinding {
  method: string;
  path: string;
  handler: string;
  framework: string;
  source_file: string;
  source_line?: number | null;
  evidence: Evidence[];
}

export interface ApiContractFinding {
  file: string;
  format: string;
  title?: string | null;
  version?: string | null;
  status: string;
  servers: string[];
  paths_count: number;
  operations_count: number;
  routes: Array<{
    method: string;
    path: string;
    operation_id?: string | null;
    summary?: string | null;
  }>;
  error_message?: string | null;
  evidence: Evidence[];
}

export interface DependencyFinding {
  name: string;
  version_spec?: string | null;
  manifest_file: string;
  is_dev: boolean;
}

export interface ModuleFinding {
  path: string;
  type: string;
  language: string;
  children_count: number;
}

export interface ConfigurationFinding {
  file: string;
  category: string;
  sensitive: boolean;
}

export interface DeploymentFinding {
  file: string;
  type: string;
}

export interface DiscoveryResult {
  snapshot_id: string;
  commit_sha: string;
  repository: {
    name: string;
    default_branch: string;
  };
  frameworks: FrameworkFinding[];
  entrypoints: EntrypointFinding[];
  routes: RouteFinding[];
  api_contracts: ApiContractFinding[];
  dependencies: DependencyFinding[];
  modules: ModuleFinding[];
  configurations: ConfigurationFinding[];
  deployment: DeploymentFinding[];
}

export interface DiscoveryRun {
  id: string;
  snapshot_id: string;
  status: DiscoveryStatus;
  started_at?: string | null;
  completed_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  metadata: DiscoveryResult;
  created_at: string;
  updated_at: string;
}

export const discoveriesApi = {
  async list(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    token?: string
  ): Promise<DiscoveryRun[]> {
    return fetchApi<DiscoveryRun[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/discoveries`,
      { token, cache: 'no-store' }
    );
  },

  async get(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    discoveryId: string,
    token?: string
  ): Promise<DiscoveryRun> {
    return fetchApi<DiscoveryRun>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/discoveries/${discoveryId}`,
      { token, cache: 'no-store' }
    );
  },

  async create(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    token?: string
  ): Promise<DiscoveryRun> {
    return fetchApi<DiscoveryRun>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/discoveries`,
      {
        method: 'POST',
        body: JSON.stringify({}),
        token,
      }
    );
  },
};
