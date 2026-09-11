import { fetchApi } from './client';

export type IntegrationPlanStatus =
  | 'PENDING'
  | 'READY'
  | 'REVIEW_REQUIRED'
  | 'BLOCKED'
  | 'COMPLETED'
  | 'FAILED';

export interface IntegrationCandidate {
  name: string;
  type: string;
  source: string;
  confidence: string;
  description?: string | null;
  evidence: Array<Record<string, unknown>>;
}

export interface RequiredCredential {
  name: string;
  type: string;
  service?: string | null;
  required: boolean;
  sensitive: boolean;
  description?: string | null;
  evidence: Array<Record<string, unknown>>;
}

export interface UnresolvedQuestion {
  id: string;
  category: string;
  question: string;
  impact: string;
  suggested_action?: string | null;
  evidence: Array<Record<string, unknown>>;
}

export interface IntegrationPlan {
  id: string;
  project_id: string;
  snapshot_id: string;
  contract_id?: string | null;
  status: IntegrationPlanStatus;
  candidates: IntegrationCandidate[];
  required_credentials: RequiredCredential[];
  unresolved_questions: UnresolvedQuestion[];
  evidence: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export const integrationPlansApi = {
  async list(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    token?: string
  ): Promise<IntegrationPlan[]> {
    return fetchApi<IntegrationPlan[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/integration-plans`,
      { token, cache: 'no-store' }
    );
  },

  async get(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    planId: string,
    token?: string
  ): Promise<IntegrationPlan> {
    return fetchApi<IntegrationPlan>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/integration-plans/${planId}`,
      { token, cache: 'no-store' }
    );
  },

  async create(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    contractId?: string,
    token?: string
  ): Promise<IntegrationPlan> {
    return fetchApi<IntegrationPlan>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/integration-plans`,
      {
        method: 'POST',
        body: JSON.stringify(contractId ? { contract_id: contractId } : {}),
        token,
      }
    );
  },
};
