import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StudioPage from '../app/(app)/studio/page';
import {
  ProjectProvider,
  CreateProjectModal,
  ProjectSelector,
  ProjectNavigation,
  ProjectStudioView,
} from '@/features/project';
import { AuthProvider } from '@/features/auth';
import { ThemeProvider } from '@/components/theme';
import { AppShell } from '@/components/layout';
import {
  projectsApi,
  organizationsApi,
  Project,
  Organization,
} from '@/lib/api';
import {
  websiteIntegrationApi,
  WebsiteIntegrationConfig,
  WebsiteAnalysis,
} from '@/lib/api/integration';
import { knowledgeApi } from '@/lib/api/knowledge';
import { assistantApi, AssistantConfig } from '@/lib/api/assistant';

// Mock websiteIntegrationApi
vi.mock('@/lib/api/integration', () => ({
  websiteIntegrationApi: {
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    validate: vi.fn(),
    getPlan: vi.fn(),
    analyze: vi.fn(),
    getLatestAnalysis: vi.fn(),
    startRun: vi.fn(),
    listRuns: vi.fn(),
    getRun: vi.fn(),
    cancelRun: vi.fn(),
    getRunDiff: vi.fn(),
    getRunPullRequest: vi.fn(),
  },
}));

// Mock knowledgeApi
vi.mock('@/lib/api/knowledge', () => ({
  knowledgeApi: {
    listDocuments: vi.fn().mockResolvedValue([]),
    getDocument: vi.fn(),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    queryKnowledge: vi.fn().mockResolvedValue({ results: [] }),
  },
}));

// Mock assistantApi
vi.mock('@/lib/api/assistant', () => ({
  assistantApi: {
    getAssistant: vi.fn(),
    updateAssistant: vi.fn(),
    resetAssistant: vi.fn(),
    getAssistantPreview: vi.fn(),
  },
}));

const mockOrg: Organization = {
  id: 'org-123',
  name: 'Acme Corp',
  slug: 'acme-corp',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockProject1: Project = {
  id: 'proj-1',
  organization_id: 'org-123',
  name: 'Storefront Assistant',
  slug: 'storefront-assistant',
  description: 'AI assistant for online retail storefront',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockProject2: Project = {
  id: 'proj-2',
  organization_id: 'org-123',
  name: 'Docs Assistant',
  slug: 'docs-assistant',
  description: 'Technical documentation bot',
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const mockWebsiteConfig: WebsiteIntegrationConfig = {
  id: 'integ-1',
  project_id: 'proj-1',
  provider: 'github',
  repository_owner: 'acme-corp',
  repository_name: 'storefront-web',
  default_branch: 'main',
  integration_branch: 'fussion/assistant-integration',
  framework_skill_id: 'nextjs-app-router',
  website_root_dir: '/',
  widget_target_path: 'app/layout.tsx',
  status: 'CONNECTED',
  has_credentials: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockAnalysis: WebsiteAnalysis = {
  id: 'analysis-1',
  integration_id: 'integ-1',
  commit_sha: 'abc123',
  framework_skill_id: 'generic-html',
  router: 'static',
  language: 'html',
  package_manager: null,
  build_command: null,
  entry_points: ['index.html'],
  integration_candidates: [{ path: 'index.html', confidence: 0.9, reason: 'Static entry page' }],
  design_tokens: {},
  protected_paths: [],
  unsupported_reason: null,
  created_at: '2026-01-01T00:00:00Z',
};

const mockAssistantConfig: AssistantConfig = {
  id: 'asst-1',
  project_id: 'proj-1',
  name: 'Storefront Concierge',
  description: 'Retail assistant',
  welcome_message: 'Hi there! How can I help you today?',
  system_instructions: 'Be helpful and concise.',
  brand_color: '#6366F1',
  text_color: '#FFFFFF',
  position: 'BOTTOM_RIGHT',
  avatar_url: '',
  starter_prompt: 'What are your return policies?',
  is_enabled: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('Fussion Project Studio — Guided Sequential UX & Website Stage', () => {
  let currentWebsiteConfig: WebsiteIntegrationConfig | null = null;
  let currentAssistantConfig: AssistantConfig = { ...mockAssistantConfig };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    currentWebsiteConfig = null;
    currentAssistantConfig = { ...mockAssistantConfig };

    // Default mocks
    vi.spyOn(organizationsApi, 'list').mockResolvedValue([mockOrg]);
    vi.spyOn(projectsApi, 'list').mockResolvedValue([mockProject1, mockProject2]);
    vi.spyOn(projectsApi, 'create').mockImplementation(async (_, input) => ({
      id: 'proj-new',
      organization_id: 'org-123',
      name: input.name,
      slug: input.slug || 'new-project',
      description: input.description || null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }));

    // Realistic stateful assistant mock
    vi.mocked(assistantApi.getAssistant).mockImplementation(async () => currentAssistantConfig);
    vi.mocked(assistantApi.getAssistantPreview).mockImplementation(async () => ({
      assistant: currentAssistantConfig,
      knowledge_base: {
        has_knowledge_base: true,
        documents_count: 1,
        ready_chunks_count: 8,
      },
      mock_preview: {
        sample_user_message: currentAssistantConfig.starter_prompt || 'What are your return policies?',
        sample_assistant_response: 'Based on 1 document in your Knowledge Base, we offer 30-day returns.',
        grounding_status: 'Online • Grounded in Knowledge Base',
      },
    }));
    vi.mocked(assistantApi.updateAssistant).mockImplementation(async (_, __, input) => {
      currentAssistantConfig = {
        ...currentAssistantConfig,
        ...input,
        name: input.name ?? currentAssistantConfig.name,
        welcome_message: input.welcome_message ?? currentAssistantConfig.welcome_message,
      };
      return currentAssistantConfig;
    });
    vi.mocked(assistantApi.resetAssistant).mockImplementation(async () => {
      currentAssistantConfig = { ...mockAssistantConfig, name: 'Fussion Assistant' };
      return currentAssistantConfig;
    });

    // Realistic stateful website integration mock
    vi.mocked(websiteIntegrationApi.get).mockImplementation(async () => {
      if (!currentWebsiteConfig) throw new Error('Not found');
      return currentWebsiteConfig;
    });
    vi.mocked(websiteIntegrationApi.create).mockImplementation(async (_, __, input) => {
      const created: WebsiteIntegrationConfig = {
        ...mockWebsiteConfig,
        repository_owner: input.repository_owner,
        repository_name: input.repository_name,
        default_branch: input.default_branch || 'main',
        framework_skill_id: input.framework_skill_id || 'nextjs-app-router',
        widget_target_path: input.widget_target_path || 'app/layout.tsx',
      };
      currentWebsiteConfig = created;
      return created;
    });
    vi.mocked(websiteIntegrationApi.delete).mockImplementation(async () => {
      currentWebsiteConfig = null;
    });
  });

  it('renders Empty Workspace with prominent "Create project" CTA when no project exists', async () => {
    vi.spyOn(projectsApi, 'list').mockResolvedValueOnce([]);

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider initialProjects={[]} initialCurrentProject={null} initialOrg={mockOrg}>
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Empty workspace elements
    expect(screen.getByTestId('empty-workspace')).toBeDefined();
    expect(screen.getByText('Welcome to Fussion')).toBeDefined();
    expect(screen.getByText(/Your workspace for building powerful AI assistants/i)).toBeDefined();

    // Prominent Create project action
    const createBtn = screen.getByTestId('create-project-trigger');
    expect(createBtn).toBeDefined();
    expect(createBtn.textContent).toContain('Create project');

    // Old flat tabs must NOT be present
    expect(screen.queryByText('Knowledge Base Foundation')).toBeNull();
    expect(screen.queryByText(/OverviewTab/i)).toBeNull();
  });

  it('opens CreateProjectModal when clicking "Create project" and validates input', async () => {
    vi.spyOn(projectsApi, 'list').mockResolvedValueOnce([]);

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider initialProjects={[]} initialCurrentProject={null} initialOrg={mockOrg}>
            <StudioPage />
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    expect(screen.queryByTestId('create-project-modal')).toBeNull();

    // Click CTA
    fireEvent.click(screen.getByTestId('create-project-trigger'));
    expect(screen.getByTestId('create-project-modal')).toBeDefined();
    expect(screen.getByText('Give your assistant a home.')).toBeDefined();

    const nameInput = screen.getByTestId('project-name-input');
    const descInput = screen.getByTestId('project-desc-input');
    expect(nameInput).toBeDefined();
    expect(descInput).toBeDefined();

    // Cancel dismisses modal
    fireEvent.click(screen.getByTestId('create-project-cancel'));
    expect(screen.queryByTestId('create-project-modal')).toBeNull();
  });

  it('submits project creation and transitions into Project Studio', async () => {
    vi.spyOn(projectsApi, 'list').mockResolvedValueOnce([]);

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider initialProjects={[]} initialCurrentProject={null} initialOrg={mockOrg}>
            <StudioPage />
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Open modal
    fireEvent.click(screen.getByTestId('create-project-trigger'));

    // Fill form
    const nameInput = screen.getByTestId('project-name-input');
    const descInput = screen.getByTestId('project-desc-input');
    fireEvent.change(nameInput, { target: { value: 'Marketing Assistant' } });
    fireEvent.change(descInput, { target: { value: 'Customer concierge for public site' } });

    // Submit
    const submitBtn = screen.getByTestId('create-project-submit');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(projectsApi.create).toHaveBeenCalledWith(
        'org-123',
        {
          name: 'Marketing Assistant',
          description: 'Customer concierge for public site',
        },
        undefined
      );
    });

    // Now in Project Studio environment
    await waitFor(() => {
      expect(screen.getByTestId('project-studio-layout')).toBeDefined();
      expect(screen.getByTestId('project-title').textContent).toBe('Marketing Assistant');
    });
  });

  it('renders Project Studio shell with BUILD, CONNECT, LIVE hierarchy and status-aware cards', () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1, mockProject2]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Project Studio Layout
    expect(screen.getByTestId('project-studio-layout')).toBeDefined();
    expect(screen.getByTestId('project-title').textContent).toBe('Storefront Assistant');

    // Contextual Navigation
    const nav = screen.getByTestId('project-navigation');
    expect(nav).toBeDefined();
    expect(within(nav).getByText('BUILD')).toBeDefined();
    expect(within(nav).getByText('CONNECT')).toBeDefined();
    expect(within(nav).getByText('LIVE')).toBeDefined();

    expect(screen.getByTestId('nav-overview')).toBeDefined();
    expect(screen.getByTestId('nav-website')).toBeDefined();
    expect(screen.getByTestId('nav-knowledge')).toBeDefined();
    expect(screen.getByTestId('nav-assistant')).toBeDefined();
    expect(screen.getByTestId('nav-integration')).toBeDefined();
    expect(screen.getByTestId('nav-preview')).toBeDefined();
    expect(screen.getByTestId('nav-settings')).toBeDefined();

    // 5-Step Stepper
    expect(screen.getByTestId('stepper-card')).toBeDefined();
    expect(screen.getByTestId('stepper-step-website')).toBeDefined();
    expect(screen.getByTestId('stepper-step-knowledge')).toBeDefined();
    expect(screen.getByTestId('stepper-step-assistant')).toBeDefined();
    expect(screen.getByTestId('stepper-step-integration')).toBeDefined();
    expect(screen.getByTestId('stepper-step-preview')).toBeDefined();

    // 5 Lifecycle Cards
    expect(screen.getByTestId('lifecycle-card-website')).toBeDefined();
    expect(screen.getByTestId('lifecycle-card-knowledge')).toBeDefined();
    expect(screen.getByTestId('lifecycle-card-assistant')).toBeDefined();
    expect(screen.getByTestId('lifecycle-card-integration')).toBeDefined();
    expect(screen.getByTestId('lifecycle-card-live')).toBeDefined();

    // Guided sequential statuses (not dead locks!)
    expect(screen.getByText('Not connected')).toBeDefined();
    expect(screen.getByText('Waiting for website')).toBeDefined();
    expect(screen.getByText('Waiting for knowledge')).toBeDefined();
    expect(screen.getByText('Waiting for assistant')).toBeDefined();
    expect(screen.getByText('Waiting for integration')).toBeDefined();

    // Recommended active action
    expect(screen.getByTestId('card-action-website').textContent).toContain('Connect website');

    // Future stages are clickable buttons
    expect(screen.getByTestId('card-action-knowledge').textContent).toContain('Website connection required');
  });

  it('navigates to StageDependencyView when clicking an unreached stage (e.g. Knowledge)', async () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Click Knowledge in sidebar
    fireEvent.click(screen.getByTestId('nav-knowledge'));

    // Friendly explanation is rendered without errors
    expect(screen.getByTestId('stage-dependency-view')).toBeDefined();
    expect(screen.getByTestId('dependency-stage-title').textContent).toBe('Your knowledge base comes next');
    expect(screen.getByText(/Your assistant needs a website connection before we can organize/i)).toBeDefined();
    expect(screen.getByTestId('dependency-status-label').textContent).toContain('Website · Not connected');
    expect(screen.getByText(/Connect your website so Fussion can discover the content/i)).toBeDefined();

    // Primary CTA takes user to Website
    const ctaBtn = screen.getByTestId('dependency-cta-button');
    expect(ctaBtn.textContent).toContain('Go to Website');
    fireEvent.click(ctaBtn);

    // Now on Website Stage View
    expect(screen.getByTestId('website-stage-view')).toBeDefined();
  });

  it('connects Website via form, updates lifecycle status, and unlocks Knowledge stage', async () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Navigate to Website stage
    fireEvent.click(screen.getByTestId('nav-website'));
    expect(screen.getByTestId('website-stage-view')).toBeDefined();

    // Verify Not Connected state renders connection form
    await waitFor(() => {
      expect(screen.getByTestId('website-connection-form')).toBeDefined();
    });

    // Fill form using sample demo button
    fireEvent.click(screen.getByTestId('fill-demo-preset'));
    expect((screen.getByTestId('repo-owner-input') as HTMLInputElement).value).toBe('acme-corp');
    expect((screen.getByTestId('repo-name-input') as HTMLInputElement).value).toBe('storefront-web');

    // Submit connection via form submit
    fireEvent.submit(screen.getByTestId('website-connection-form'));

    // Verify API called
    await waitFor(() => {
      expect(websiteIntegrationApi.create).toHaveBeenCalledWith(
        'org-123',
        'proj-1',
        expect.objectContaining({
          repository_owner: 'acme-corp',
          repository_name: 'storefront-web',
          default_branch: 'main',
        })
      );
    });

    // Verify Connected state panel is now rendered
    await waitFor(() => {
      expect(screen.getByTestId('website-connected-panel')).toBeDefined();
      expect(screen.getByTestId('connected-repo-name').textContent).toBe('acme-corp/storefront-web');
      expect(screen.getByTestId('advance-to-knowledge')).toBeDefined();
    });

    // Advance to Knowledge
    fireEvent.click(screen.getByTestId('advance-to-knowledge'));

    // Because Website is completed, Knowledge is now actionable and shows stage view, NOT dependency blocker!
    expect(screen.getByTestId('stage-view-knowledge')).toBeDefined();
    expect(screen.queryByTestId('stage-dependency-view')).toBeNull();

    // Return to Website stage - remains accessible in configured state
    fireEvent.click(screen.getByTestId('nav-website'));
    await waitFor(() => {
      expect(screen.getByTestId('website-connected-panel')).toBeDefined();
    });

    // Disconnect website
    fireEvent.click(screen.getByTestId('disconnect-website-button'));
    await waitFor(() => {
      expect(websiteIntegrationApi.delete).toHaveBeenCalledWith('org-123', 'proj-1');
      expect(screen.getByTestId('website-connection-form')).toBeDefined();
    });
  });

  it('detects the framework and integration point from the repository analysis', async () => {
    currentWebsiteConfig = { ...mockWebsiteConfig };
    vi.mocked(websiteIntegrationApi.get).mockResolvedValue(mockWebsiteConfig);
    vi.mocked(websiteIntegrationApi.getLatestAnalysis).mockResolvedValue(null);
    vi.mocked(websiteIntegrationApi.analyze).mockResolvedValue(mockAnalysis);

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    fireEvent.click(screen.getByTestId('nav-website'));
    await waitFor(() => {
      expect(screen.getByTestId('website-connected-panel')).toBeDefined();
    });

    // The framework and target are detected, never chosen: no dropdown, no typed path.
    expect(screen.queryByTestId('framework-select')).toBeNull();
    expect(screen.queryByTestId('widget-target-input')).toBeNull();

    fireEvent.click(screen.getByTestId('analyze-website-button'));

    await waitFor(() => {
      expect(websiteIntegrationApi.analyze).toHaveBeenCalledWith('org-123', 'proj-1');
      // The analysis drives the display: config says nextjs-app-router, the analyst says
      // generic-html, and the detected values must be the analyst's.
      expect(screen.getByTestId('detected-framework').textContent).toBe('generic-html');
      expect(screen.getByTestId('detected-target').textContent).toBe('index.html');
    });
  });

  it('displays error banner if website connection fails', async () => {
    vi.mocked(websiteIntegrationApi.create).mockRejectedValueOnce(
      new Error('GitHub repository not found or insufficient permissions.')
    );

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Navigate to Website stage
    fireEvent.click(screen.getByTestId('nav-website'));
    await waitFor(() => {
      expect(screen.getByTestId('website-connection-form')).toBeDefined();
    });

    // Fill form and submit
    fireEvent.change(screen.getByTestId('repo-owner-input'), { target: { value: 'invalid-owner' } });
    fireEvent.change(screen.getByTestId('repo-name-input'), { target: { value: 'invalid-repo' } });
    fireEvent.submit(screen.getByTestId('website-connection-form'));

    // Verify error banner is shown
    await waitFor(() => {
      expect(screen.getByTestId('website-error-banner')).toBeDefined();
      expect(screen.getByText(/GitHub repository not found/i)).toBeDefined();
    });

    // Dismiss error
    fireEvent.click(screen.getByText('Dismiss'));
    expect(screen.queryByTestId('website-error-banner')).toBeNull();
  });

  it('allows switching projects and returning to workspace via All projects button', async () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1, mockProject2]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Header selector displays active project
    const selectorBtn = screen.getByTestId('project-selector-button');
    expect(selectorBtn.textContent).toContain('Storefront Assistant');

    // Open dropdown and switch
    fireEvent.click(selectorBtn);
    fireEvent.click(screen.getByTestId('project-option-proj-2'));
    expect(screen.getByTestId('project-title').textContent).toBe('Docs Assistant');

    // Click "All projects" at the bottom of the sidebar
    fireEvent.click(screen.getByTestId('nav-all-projects'));

    // Returns to Empty Workspace
    expect(screen.getByTestId('empty-workspace')).toBeDefined();
  });

  it('renders notification bell and account trigger with chevron down in AppHeader', () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    expect(screen.getByTestId('notification-bell-button')).toBeDefined();
    expect(screen.getByTestId('account-menu-button')).toBeDefined();
  });

  it('renders WebsiteStageView stably without re-render loop on unconfigured project', async () => {
    vi.mocked(websiteIntegrationApi.get).mockRejectedValueOnce(new Error('Not found'));

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Navigate to website stage
    fireEvent.click(screen.getByTestId('nav-website'));

    await waitFor(() => {
      expect(screen.getByTestId('website-stage-view')).toBeDefined();
    });

    // Form is displayed stably
    await waitFor(() => {
      expect(screen.getByTestId('website-connection-form')).toBeDefined();
    });

    expect(screen.getByTestId('repo-owner-input')).toBeDefined();
    expect(screen.getByTestId('repo-name-input')).toBeDefined();
  });

  it('renders StageDependencyView when Knowledge stage is selected before Website is connected', async () => {
    vi.mocked(websiteIntegrationApi.get).mockRejectedValueOnce(new Error('Not found'));

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Click Knowledge stage in sidebar
    fireEvent.click(screen.getByTestId('nav-knowledge'));

    // Verify dependency view is rendered explaining the prerequisite
    await waitFor(() => {
      expect(screen.getByTestId('stage-dependency-view')).toBeDefined();
    });

    expect(screen.getByText('Your knowledge base comes next')).toBeDefined();
    expect(screen.getByText('Website · Not connected')).toBeDefined();

    // Upload mutation controls must NOT be rendered before Website is connected
    expect(screen.queryByTestId('knowledge-stage-view')).toBeNull();
    expect(screen.queryByText('Upload business knowledge documents')).toBeNull();

    // Clicking "Go to Website →" in dependency blocker routes user to Website stage
    fireEvent.click(screen.getByTestId('dependency-cta-button'));
    await waitFor(() => {
      expect(screen.getByTestId('website-stage-view')).toBeDefined();
    });
  });

  it('renders KnowledgeStageView when Website is connected, mounts 3 pillars, and marks stage completed upon READY documents', async () => {
    // Website is connected
    currentWebsiteConfig = mockWebsiteConfig;

    // Knowledge has a READY document
    const mockReadyDoc = {
      id: 'doc-ready-1',
      knowledge_base_id: 'kb-1',
      filename: 'company-handbook.pdf',
      content_type: 'application/pdf',
      file_size_bytes: 20480,
      status: 'READY' as const,
      error_message: null,
      chunks_count: 8,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    vi.mocked(knowledgeApi.listDocuments).mockResolvedValue([mockReadyDoc]);

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Navigate to Website stage first, verifying connected status
    fireEvent.click(screen.getByTestId('nav-website'));
    await waitFor(() => {
      expect(screen.getByTestId('website-connected-panel')).toBeDefined();
    });

    // Advance to Knowledge via completion banner CTA
    fireEvent.click(screen.getByTestId('advance-to-knowledge'));

    // Renders native KnowledgeStageView (not dependency view)
    await waitFor(() => {
      expect(screen.getByTestId('knowledge-stage-view')).toBeDefined();
    });
    expect(screen.queryByTestId('stage-dependency-view')).toBeNull();

    // Pillar 1: Upload Source
    expect(screen.getByText('Upload business knowledge documents')).toBeDefined();

    // Pillar 2: Document Library
    await waitFor(() => {
      expect(screen.getByText('company-handbook.pdf')).toBeDefined();
      expect(screen.getByText('8')).toBeDefined(); // chunk count
    });

    // Pillar 3: Grounding Bench
    expect(screen.getByText('Test Knowledge Retrieval')).toBeDefined();

    // Metrics Strip
    expect(screen.getByTestId('knowledge-metrics-strip')).toBeDefined();
    expect(screen.getByText('8 chunks')).toBeDefined();

    // Completion Status Badge & Banner
    expect(screen.getByTestId('knowledge-ready-badge')).toBeDefined();
    expect(screen.getByTestId('knowledge-completion-banner')).toBeDefined();
    expect(screen.getByText('Next Recommended Stage: Assistant Configuration')).toBeDefined();

    // Advance to Assistant
    fireEvent.click(screen.getByTestId('advance-to-assistant'));

    // Because Knowledge is completed, Assistant is actionable
    await waitFor(() => {
      expect(screen.getByTestId('stage-view-assistant')).toBeDefined();
    });

    // Navigate to Overview
    fireEvent.click(screen.getByTestId('nav-overview'));
    await waitFor(() => {
      expect(screen.getByTestId('project-studio-view')).toBeDefined();
    });

    // Overview stepper reflects Knowledge is completed
    const knowledgeStepperStep = screen.getByTestId('stepper-step-knowledge');
    expect(within(knowledgeStepperStep).getByText('Completed')).toBeDefined();
  });

  it('Assistant stage renders StageDependencyView when Knowledge is not completed', async () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // Click Assistant directly from navigation before Knowledge is complete
    fireEvent.click(screen.getByTestId('nav-assistant'));

    // Shows sequential dependency explanation
    await waitFor(() => {
      expect(screen.getByTestId('stage-dependency-view')).toBeDefined();
    });
    expect(screen.getByTestId('dependency-stage-title').textContent).toContain('Your assistant comes next');
    expect(screen.getByTestId('dependency-status-label').textContent).toContain('Knowledge base not configured');

    // No editing forms or preview should be rendered
    expect(screen.queryByTestId('assistant-stage-view')).toBeNull();

    // CTA routes directly to prerequisite stage (Knowledge)
    const ctaBtn = screen.getByTestId('dependency-cta-button');
    fireEvent.click(ctaBtn);

    // Knowledge is now active (showing its dependency view if website not connected)
    await waitFor(() => {
      expect(screen.getByTestId('stage-dependency-view')).toBeDefined();
      expect(screen.getByTestId('dependency-stage-title').textContent).toContain('Your knowledge base comes next');
    });
  });

  it('Assistant stage renders AssistantStageView, enforces 4-tier readiness progression, and unlocks Integration upon assertion', async () => {
    currentWebsiteConfig = mockWebsiteConfig;

    const mockReadyDoc = {
      id: 'doc-ready-1',
      knowledge_base_id: 'kb-1',
      filename: 'company-handbook.pdf',
      content_type: 'application/pdf',
      file_size_bytes: 20480,
      status: 'READY' as const,
      error_message: null,
      chunks_count: 8,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    vi.mocked(knowledgeApi.listDocuments).mockResolvedValue([mockReadyDoc]);

    render(
      <ThemeProvider>
        <AuthProvider>
          <ProjectProvider
            initialProjects={[mockProject1]}
            initialCurrentProject={mockProject1}
            initialOrg={mockOrg}
          >
            <AppShell>
              <StudioPage />
            </AppShell>
          </ProjectProvider>
        </AuthProvider>
      </ThemeProvider>
    );

    // 1. Complete Website stage
    fireEvent.click(screen.getByTestId('nav-website'));
    await waitFor(() => {
      expect(screen.getByTestId('website-connected-panel')).toBeDefined();
    });

    // 2. Complete Knowledge stage
    fireEvent.click(screen.getByTestId('advance-to-knowledge'));
    await waitFor(() => {
      expect(screen.getByTestId('knowledge-ready-badge')).toBeDefined();
    });

    // 3. Advance to Assistant stage
    fireEvent.click(screen.getByTestId('advance-to-assistant'));
    await waitFor(() => {
      expect(screen.getByTestId('assistant-stage-view')).toBeDefined();
    });
    expect(screen.queryByTestId('stage-dependency-view')).toBeNull();

    // Verify Studio Header
    expect(screen.getByText(/Assistant Voice & Widget Studio/i)).toBeDefined();
    expect(screen.getByText(/BUILD · Stage 3 of 5/i)).toBeDefined();

    // Verify Metrics Strip
    expect(screen.getByTestId('assistant-metrics-strip')).toBeDefined();
    expect(screen.getByText('1 Document(s)')).toBeDefined();

    // Verify 3 Configuration Pillars
    expect(screen.getByDisplayValue('Storefront Concierge')).toBeDefined();
    expect(screen.getByDisplayValue('Hi there! How can I help you today?')).toBeDefined();
    expect(screen.getByDisplayValue('What are your return policies?')).toBeDefined();
    expect(screen.getByText(/Appearance & Widget Styling/i)).toBeDefined();
    expect(screen.getByText(/Behavior & Grounding Instructions/i)).toBeDefined();

    // Verify Live Preview Simulation
    expect(screen.getByText(/Live Interactive Preview/i)).toBeDefined();
    expect(screen.getByText(/Mock Simulation/i)).toBeDefined();

    // 4. Edit form -> triggers Draft state with Unsaved Changes save bar
    const nameInput = screen.getByDisplayValue('Storefront Concierge');
    fireEvent.change(nameInput, { target: { value: 'Fussion VIP Bot' } });

    await waitFor(() => {
      expect(screen.getByText(/Unsaved Changes/i)).toBeDefined();
    });

    // 5. Save Changes -> persists configuration and asserts Ready for Integration
    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(assistantApi.updateAssistant).toHaveBeenCalledWith(
        'org-123',
        'proj-1',
        expect.objectContaining({ name: 'Fussion VIP Bot' })
      );
      expect(screen.getByTestId('assistant-ready-badge')).toBeDefined();
    });

    // Readiness Assertion & Handoff Banner
    expect(screen.getByTestId('assistant-handoff-banner')).toBeDefined();
    expect(screen.getByText('Your assistant is configured and grounded')).toBeDefined();
    const startIntegrationBtn = screen.getByTestId('start-integration-cta');
    expect(startIntegrationBtn).toBeDefined();

    // 6. Click Start Integration -> advances to Integration stage
    fireEvent.click(startIntegrationBtn);
    await waitFor(() => {
      // Integration stage is rendered (or generic view since Stage 4 is next)
      expect(screen.queryByTestId('assistant-stage-view')).toBeNull();
    });

    // 7. Check Overview Stepper completion
    fireEvent.click(screen.getByTestId('nav-overview'));
    await waitFor(() => {
      expect(screen.getByTestId('project-studio-view')).toBeDefined();
    });

    const assistantStepperStep = screen.getByTestId('stepper-step-assistant');
    expect(within(assistantStepperStep).getByText('Completed')).toBeDefined();
  });
});
