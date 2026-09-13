import { fetchApi } from './client';

export type WebsiteIntegrationStatus =
  | 'NOT_CONNECTED'
  | 'CONNECTED'
  | 'PLANNING'
  | 'SANDBOX_READY'
  | 'GENERATING'
  | 'VALIDATING'
  | 'READY_FOR_PR'
  | 'PR_CREATED'
  | 'FAILED';

export type IntegrationRunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'VALIDATING'
  | 'READY_FOR_PR'
  | 'PR_CREATED'
  | 'FAILED'
  | 'CANCELLED';

export interface WebsiteIntegrationConfig {
  id: string;
  project_id: string;
  provider: string;
  repository_owner: string;
  repository_name: string;
  default_branch: string;
  integration_branch?: string | null;
  framework_skill_id: string;
  website_root_dir: string;
  widget_target_path: string;
  status: WebsiteIntegrationStatus;
  has_credentials: boolean;
  github_installation_id?: number | null;
  last_error?: string | null;
  last_success_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WebsiteIntegrationCreateInput {
  repository_owner: string;
  repository_name: string;
  default_branch?: string;
  framework_skill_id?: string;
  website_root_dir?: string;
  widget_target_path?: string;
  github_token?: string;
  github_installation_id?: number;
}

export interface WebsiteIntegrationUpdateInput {
  repository_owner?: string;
  repository_name?: string;
  default_branch?: string;
  framework_skill_id?: string;
  website_root_dir?: string;
  widget_target_path?: string;
  github_token?: string;
}

export interface IntegrationCandidate {
  path: string;
  confidence: number;
  reason: string;
}

export interface WebsiteAnalysis {
  id: string;
  integration_id: string;
  commit_sha: string;
  framework_skill_id: string | null;
  router: string | null;
  language: string | null;
  package_manager: string | null;
  build_command: string | null;
  entry_points: string[];
  integration_candidates: IntegrationCandidate[];
  design_tokens: Record<string, unknown>;
  protected_paths: string[];
  unsupported_reason: string | null;
  created_at: string;
}

export interface IntegrationPlanPayload {
  framework_skill_id: string;
  files_to_create: string[];
  files_to_modify: string[];
  files_to_delete: string[];
  warnings: string[];
  summary?: string | null;
}

export interface IntegrationRun {
  id: string;
  integration_id: string;
  status: IntegrationRunStatus;
  branch_name: string;
  commit_sha?: string | null;
  pull_request_number?: number | null;
  pull_request_url?: string | null;
  sandbox_ref: string;
  plan_summary: Record<string, unknown>;
  generated_files_count: number;
  modified_files_count: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ValidationResultPayload {
  status: string;
  is_valid: boolean;
  repository: string;
  owner: string;
  repo: string;
  default_branch: string;
  framework_skill_id: string;
  assistant_readiness: boolean;
  knowledge_base_readiness: boolean;
  issues: string[];
}

export interface DiffFileItem {
  path: string;
  action: string;
  diff: string;
}

export interface RunDiffPayload {
  run_id: string;
  files: DiffFileItem[];
  summary: string;
}

export interface PullRequestInfo {
  pull_request_number?: number | null;
  pull_request_url?: string | null;
  branch_name: string;
  base_branch: string;
  title: string;
  status: string;
}

export const websiteIntegrationApi = {
  get: async (orgId: string, projectId: string, token?: string): Promise<WebsiteIntegrationConfig> => {
    return fetchApi<WebsiteIntegrationConfig>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations`,
      { token, cache: 'no-store' }
    );
  },

  create: async (
    orgId: string,
    projectId: string,
    data: WebsiteIntegrationCreateInput,
    token?: string
  ): Promise<WebsiteIntegrationConfig> => {
    return fetchApi<WebsiteIntegrationConfig>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations`,
      {
        method: 'POST',
        body: JSON.stringify(data),
        token,
      }
    );
  },

  analyze: async (orgId: string, projectId: string, token?: string): Promise<WebsiteAnalysis> => {
    return fetchApi<WebsiteAnalysis>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/analyze`,
      { method: 'POST', token }
    );
  },

  getLatestAnalysis: async (
    orgId: string,
    projectId: string,
    token?: string
  ): Promise<WebsiteAnalysis | null> => {
    return fetchApi<WebsiteAnalysis | null>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/analysis`,
      { token, cache: 'no-store' }
    );
  },

  update: async (
    orgId: string,
    projectId: string,
    data: WebsiteIntegrationUpdateInput,
    token?: string
  ): Promise<WebsiteIntegrationConfig> => {
    return fetchApi<WebsiteIntegrationConfig>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations`,
      {
        method: 'PATCH',
        body: JSON.stringify(data),
        token,
      }
    );
  },

  delete: async (orgId: string, projectId: string, token?: string): Promise<void> => {
    return fetchApi<void>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations`,
      { method: 'DELETE', token }
    );
  },

  validate: async (
    orgId: string,
    projectId: string,
    token?: string
  ): Promise<ValidationResultPayload> => {
    return fetchApi<ValidationResultPayload>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/validate`,
      { method: 'POST', token }
    );
  },

  getPlan: async (
    orgId: string,
    projectId: string,
    token?: string
  ): Promise<IntegrationPlanPayload> => {
    return fetchApi<IntegrationPlanPayload>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/plan`,
      { token, cache: 'no-store' }
    );
  },

  startRun: async (orgId: string, projectId: string, token?: string): Promise<IntegrationRun> => {
    return fetchApi<IntegrationRun>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/runs`,
      { method: 'POST', token }
    );
  },

  listRuns: async (
    orgId: string,
    projectId: string,
    token?: string
  ): Promise<IntegrationRun[]> => {
    return fetchApi<IntegrationRun[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/runs`,
      { token, cache: 'no-store' }
    );
  },

  getRun: async (
    orgId: string,
    projectId: string,
    runId: string,
    token?: string
  ): Promise<IntegrationRun> => {
    return fetchApi<IntegrationRun>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/runs/${runId}`,
      { token, cache: 'no-store' }
    );
  },

  cancelRun: async (
    orgId: string,
    projectId: string,
    runId: string,
    token?: string
  ): Promise<IntegrationRun> => {
    return fetchApi<IntegrationRun>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/runs/${runId}/cancel`,
      { method: 'POST', token }
    );
  },

  getRunDiff: async (
    orgId: string,
    projectId: string,
    runId: string,
    token?: string
  ): Promise<RunDiffPayload> => {
    return fetchApi<RunDiffPayload>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/runs/${runId}/diff`,
      { token, cache: 'no-store' }
    );
  },

  getRunPullRequest: async (
    orgId: string,
    projectId: string,
    runId: string,
    token?: string
  ): Promise<PullRequestInfo> => {
    return fetchApi<PullRequestInfo>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/website-integrations/runs/${runId}/pull-request`,
      { token, cache: 'no-store' }
    );
  },
};
