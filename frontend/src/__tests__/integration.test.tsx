import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  IntegrationView,
  RepositoryConnectionForm,
  IntegrationStatus,
  IntegrationPlan,
  SandboxPreview,
  IntegrationActions,
  PullRequestCard,
  IntegrationHistory,
} from '@/features/integrations';
import {
  websiteIntegrationApi,
  WebsiteIntegrationConfig,
  IntegrationPlanPayload,
  IntegrationRun,
  ValidationResultPayload,
  RunDiffPayload,
  PullRequestInfo,
} from '@/lib/api/integration';

// Mock websiteIntegrationApi
vi.mock('@/lib/api/integration', () => ({
  websiteIntegrationApi: {
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    validate: vi.fn(),
    getPlan: vi.fn(),
    startRun: vi.fn(),
    listRuns: vi.fn(),
    getRun: vi.fn(),
    cancelRun: vi.fn(),
    getRunDiff: vi.fn(),
    getRunPullRequest: vi.fn(),
  },
}));

const mockConfig: WebsiteIntegrationConfig = {
  id: 'integ-111',
  project_id: 'proj-100',
  provider: 'github',
  repository_owner: 'acme-corp',
  repository_name: 'storefront',
  default_branch: 'main',
  integration_branch: 'fussion/assistant-integration',
  framework: 'REACT_NEXTJS',
  website_root_dir: '/',
  widget_target_path: 'app/layout.tsx',
  status: 'CONNECTED',
  has_credentials: true,
  created_at: '2026-03-01T10:00:00Z',
  updated_at: '2026-03-01T12:00:00Z',
};

const mockPlan: IntegrationPlanPayload = {
  framework: 'REACT_NEXTJS',
  files_to_create: ['components/fussion/FussionAssistant.tsx'],
  files_to_modify: ['app/layout.tsx'],
  files_to_delete: [],
  warnings: [],
  summary: 'Plan to integrate assistant widget',
};

const mockValidation: ValidationResultPayload = {
  status: 'valid',
  is_valid: true,
  repository: 'acme-corp/storefront',
  owner: 'acme-corp',
  repo: 'storefront',
  default_branch: 'main',
  framework: 'REACT_NEXTJS',
  assistant_readiness: true,
  knowledge_base_readiness: true,
  issues: [],
};

const mockRun: IntegrationRun = {
  id: 'run-999',
  integration_id: 'integ-111',
  status: 'PR_CREATED',
  branch_name: 'fussion/assistant-integration',
  commit_sha: '1234567890abcdef1234567890abcdef12345678',
  pull_request_number: 42,
  pull_request_url: 'https://github.com/acme-corp/storefront/pull/42',
  sandbox_ref: 'sandbox-123',
  plan_summary: {},
  generated_files_count: 1,
  modified_files_count: 1,
  error_message: null,
  created_at: '2026-03-01T13:00:00Z',
  updated_at: '2026-03-01T13:02:00Z',
};

const mockDiff: RunDiffPayload = {
  run_id: 'run-999',
  files: [
    {
      path: 'components/fussion/FussionAssistant.tsx',
      action: 'create',
      diff: '+ "use client";\n+ export function FussionAssistant() { return <div />; }',
    },
    {
      path: 'app/layout.tsx',
      action: 'modify',
      diff: '+ import { FussionAssistant } from "./components/fussion/FussionAssistant";',
    },
  ],
  summary: 'Created 1 file, modified 1 file',
};

const mockPR: PullRequestInfo = {
  pull_request_number: 42,
  pull_request_url: 'https://github.com/acme-corp/storefront/pull/42',
  branch_name: 'fussion/assistant-integration',
  base_branch: 'main',
  title: 'Integrate Fussion Assistant',
  status: 'open',
};

describe('Website Integration Feature Tests (Phase 11)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(websiteIntegrationApi.get).mockResolvedValue(mockConfig);
    vi.mocked(websiteIntegrationApi.listRuns).mockResolvedValue([mockRun]);
    vi.mocked(websiteIntegrationApi.validate).mockResolvedValue(mockValidation);
    vi.mocked(websiteIntegrationApi.getPlan).mockResolvedValue(mockPlan);
    vi.mocked(websiteIntegrationApi.getRunDiff).mockResolvedValue(mockDiff);
    vi.mocked(websiteIntegrationApi.getRunPullRequest).mockResolvedValue(mockPR);
  });

  describe('IntegrationView Rendering & Project Scoping', () => {
    it('shows placeholder when no project is selected', () => {
      render(<IntegrationView />);
      expect(screen.getByText(/No Project Selected/i)).toBeDefined();
    });

    it('renders loaded integration configuration and status', async () => {
      render(<IntegrationView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText(/Automated Website Integration & Pull Request Pipeline/i)).toBeDefined();
      });

      expect(screen.getByDisplayValue('acme-corp')).toBeDefined();
      expect(screen.getByDisplayValue('storefront')).toBeDefined();
      expect(screen.getByDisplayValue('main')).toBeDefined();
      expect(screen.getByText('Connected')).toBeDefined();
    });
  });

  describe('Repository Connection Form & Saving', () => {
    it('updates form fields on change', async () => {
      render(<IntegrationView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('storefront')).toBeDefined();
      });

      const repoInput = screen.getByDisplayValue('storefront');
      fireEvent.change(repoInput, { target: { value: 'storefront-v2' } });

      expect(screen.getByDisplayValue('storefront-v2')).toBeDefined();
    });

    it('submits updated configuration when clicking Update Configuration', async () => {
      const updatedConfig = { ...mockConfig, repository_name: 'storefront-v2' };
      vi.mocked(websiteIntegrationApi.update).mockResolvedValue(updatedConfig);

      render(<IntegrationView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('storefront')).toBeDefined();
      });

      const repoInput = screen.getByDisplayValue('storefront');
      fireEvent.change(repoInput, { target: { value: 'storefront-v2' } });

      const saveBtn = screen.getByRole('button', { name: /Update Configuration/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(websiteIntegrationApi.update).toHaveBeenCalledWith(
          'org-1',
          'proj-100',
          expect.objectContaining({ repository_name: 'storefront-v2' })
        );
        expect(screen.getByText(/Integration configuration updated/i)).toBeDefined();
      });
    });

    it('deletes configuration when Delete Connection is clicked with confirmation', async () => {
      vi.mocked(websiteIntegrationApi.delete).mockResolvedValue();
      vi.spyOn(window, 'confirm').mockReturnValue(true);

      render(<IntegrationView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('storefront')).toBeDefined();
      });

      const deleteBtn = screen.getByRole('button', { name: /Delete Connection/i });
      fireEvent.click(deleteBtn);

      await waitFor(() => {
        expect(websiteIntegrationApi.delete).toHaveBeenCalledWith('org-1', 'proj-100');
        expect(screen.getByText(/Website integration deleted/i)).toBeDefined();
      });
    });
  });

  describe('Validation & Plan Generation', () => {
    it('runs connection validation when clicking Validate Connection', async () => {
      render(<IntegrationView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText(/Automated Website Integration/i)).toBeDefined();
      });

      const validateBtn = screen.getByRole('button', { name: /Validate Connection/i });
      fireEvent.click(validateBtn);

      await waitFor(() => {
        expect(websiteIntegrationApi.validate).toHaveBeenCalledWith('org-1', 'proj-100');
        expect(screen.getByText(/Repository connection & branch validation passed/i)).toBeDefined();
      });
    });

    it('generates integration plan and displays file changes', async () => {
      render(<IntegrationView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText(/Automated Website Integration/i)).toBeDefined();
      });

      const planBtn = screen.getAllByRole('button', { name: /Generate Plan/i })[0];
      fireEvent.click(planBtn);

      await waitFor(() => {
        expect(websiteIntegrationApi.getPlan).toHaveBeenCalledWith('org-1', 'proj-100');
        expect(screen.getByText(/Deterministic integration plan generated/i)).toBeDefined();
      });

      expect(screen.getByText('components/fussion/FussionAssistant.tsx')).toBeDefined();
      expect(screen.getByText('app/layout.tsx')).toBeDefined();
    });
  });

  describe('Pipeline Run Execution & Pull Request Creation', () => {
    it('executes pipeline and opens PR card on success', async () => {
      vi.mocked(websiteIntegrationApi.startRun).mockResolvedValue(mockRun);

      render(<IntegrationView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText(/Automated Website Integration/i)).toBeDefined();
      });

      const executeBtn = screen.getByRole('button', { name: /Create Pull Request/i });
      expect(executeBtn).toBeDefined();
      fireEvent.click(executeBtn);

      await waitFor(() => {
        expect(websiteIntegrationApi.startRun).toHaveBeenCalledWith('org-1', 'proj-100');
        expect(screen.getByText(/Pull Request #42 created successfully!/i)).toBeDefined();
      });

      expect(screen.getByText('#42')).toBeDefined();
      expect(screen.getByText(/Production Safety Notice/i)).toBeDefined();
    });

    it('displays run history and allows viewing diff', async () => {
      render(<IntegrationView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText(/Integration Run History/i)).toBeDefined();
      });

      // Shows existing run in table
      expect(screen.getByText('PR #42')).toBeDefined();

      const viewDiffBtn = screen.getByRole('button', { name: /Diff/i });
      fireEvent.click(viewDiffBtn);

      await waitFor(() => {
        expect(websiteIntegrationApi.getRunDiff).toHaveBeenCalledWith('org-1', 'proj-100', 'run-999');
        expect(screen.getByText(/FussionAssistant.tsx/i)).toBeDefined();
      });
    });
  });

  describe('Direct Component Unit Tests', () => {
    it('PullRequestCard renders PR link and safe human review badges', () => {
      render(<PullRequestCard pr={mockPR} />);

      expect(screen.getByText('Integrate Fussion Assistant')).toBeDefined();
      expect(screen.getByText('#42')).toBeDefined();
      expect(screen.getByText('fussion/assistant-integration')).toBeDefined();
      expect(screen.getByText(/Production Safety Notice/i)).toBeDefined();
      expect(screen.getByRole('link', { name: /Review on GitHub/i })).toBeDefined();
    });

    it('SandboxPreview displays zero arbitrary code execution badge', () => {
      render(<SandboxPreview validation={mockValidation} />);

      expect(screen.getByText(/Sandbox Security & Static Validation/i)).toBeDefined();
      expect(screen.getByText(/Sandbox Isolation & Containment/i)).toBeDefined();
      expect(screen.getByText(/Path Traversal & Device Protection/i)).toBeDefined();
      expect(screen.getByText(/Static Credential Sanitization/i)).toBeDefined();
      expect(screen.getByText(/Zero Repository Execution/i)).toBeDefined();
    });

    it('IntegrationStatus renders correct badge and metadata', () => {
      render(<IntegrationStatus config={mockConfig} latestRun={mockRun} />);

      expect(screen.getByText('Connected')).toBeDefined();
      expect(screen.getByText('acme-corp/storefront')).toBeDefined();
      expect(screen.getByText('Blueprint Ready')).toBeDefined();
      expect(screen.getByText('Grounding Enabled')).toBeDefined();
      expect(screen.getByText('PR_CREATED')).toBeDefined();
    });

    it('IntegrationActions disables execute when canExecute is false', () => {
      const onValidate = vi.fn();
      const onGeneratePlan = vi.fn();
      const onExecute = vi.fn();

      render(
        <IntegrationActions
          config={mockConfig}
          plan={null}
          isValidating={false}
          isPlanning={false}
          isExecuting={false}
          canExecute={false}
          onValidate={onValidate}
          onGeneratePlan={onGeneratePlan}
          onExecute={onExecute}
        />
      );

      const executeBtn = screen.getByRole('button', { name: /Create Pull Request/i });
      expect(executeBtn.hasAttribute('disabled')).toBe(true);
    });
  });
});
