import {
  WebsiteIntegrationConfig,
  IntegrationRun,
  IntegrationPlanPayload,
  ValidationResultPayload,
  RunDiffPayload,
  PullRequestInfo,
} from '@/lib/api/integration';

export type {
  WebsiteIntegrationConfig,
  IntegrationRun,
  IntegrationPlanPayload,
  ValidationResultPayload,
  RunDiffPayload,
  PullRequestInfo,
};

export interface IntegrationFormState {
  repository_owner: string;
  repository_name: string;
  default_branch: string;
  website_root_dir: string;
  github_token: string;
}

export interface IntegrationViewState {
  config: WebsiteIntegrationConfig | null;
  form: IntegrationFormState;
  plan: IntegrationPlanPayload | null;
  validation: ValidationResultPayload | null;
  latestRun: IntegrationRun | null;
  runs: IntegrationRun[];
  selectedRunDiff: RunDiffPayload | null;
  selectedPR: PullRequestInfo | null;
  isLoading: boolean;
  isSaving: boolean;
  isValidating: boolean;
  isPlanning: boolean;
  isExecuting: boolean;
  error: string | null;
  successMessage: string | null;
}
