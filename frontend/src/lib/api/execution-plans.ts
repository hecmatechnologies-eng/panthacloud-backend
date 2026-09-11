import { fetchApi } from './client';

export type ExecutionPlanStatus =
  | 'DRAFT'
  | 'READY'
  | 'REQUIRES_APPROVAL'
  | 'BLOCKED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type SafetyClassification =
  | 'CONFIGURATION'
  | 'READ_ONLY'
  | 'WRITE'
  | 'DESTRUCTIVE'
  | 'EXTERNAL_NETWORK'
  | 'CREDENTIAL_REQUIRED';

export interface ExecutionStep {
  step_id: string;
  step_number: number;
  name: string;
  action_type: string;
  adapter_id?: string | null;
  operation_id?: string | null;
  safety_classification: SafetyClassification;
  requires_approval: boolean;
  status: string;
  blocked_reason?: string | null;
  depends_on: string[];
  inputs: Record<string, unknown>;
  evidence?: Record<string, unknown> | Array<unknown> | null;
}

export interface ExecutionPlan {
  id: string;
  project_id: string;
  snapshot_id: string;
  integration_plan_id?: string | null;
  name: string;
  status: ExecutionPlanStatus;
  version: number;
  steps: ExecutionStep[];
  blocked_reasons: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export const executionPlansApi = {
  async list(
    orgId: string,
    projectId: string,
    repositoryId: string,
    snapshotId: string,
    token?: string
  ): Promise<ExecutionPlan[]> {
    return fetchApi<ExecutionPlan[]>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/execution-plans`,
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
  ): Promise<ExecutionPlan> {
    return fetchApi<ExecutionPlan>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/execution-plans/${planId}`,
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
  ): Promise<ExecutionPlan> {
    return fetchApi<ExecutionPlan>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/repositories/${repositoryId}/snapshots/${snapshotId}/execution-plans`,
      {
        method: 'POST',
        body: JSON.stringify(integrationPlanId ? { integration_plan_id: integrationPlanId } : {}),
        token,
      }
    );
  },
};
