import {
  WebsiteIntegrationConfig,
  IntegrationRun,
  IntegrationPlanPayload,
  ValidationResultPayload,
  RunDiffPayload,
  PullRequestInfo,
  WebsiteFramework,
} from '@/lib/api/integration';

export type {
  WebsiteIntegrationConfig,
  IntegrationRun,
  IntegrationPlanPayload,
  ValidationResultPayload,
  RunDiffPayload,
  PullRequestInfo,
  WebsiteFramework,
};

export interface IntegrationFormState {
  repository_owner: string;
  repository_name: string;
  default_branch: string;
  framework: WebsiteFramework;
  website_root_dir: string;
  widget_target_path: string;
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
