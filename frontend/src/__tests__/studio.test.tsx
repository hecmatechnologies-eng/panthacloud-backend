import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { StudioHeader } from '../components/studio/StudioHeader';
import { StudioNavigation } from '../components/studio/StudioNavigation';
import { OverviewTab } from '../components/studio/tabs/OverviewTab';
import { WebsiteTab } from '../components/studio/tabs/WebsiteTab';
import { KnowledgeTab } from '../components/studio/tabs/KnowledgeTab';
import { AssistantTab } from '../components/studio/tabs/AssistantTab';
import { IntegrationTab } from '../components/studio/tabs/IntegrationTab';
import { DiagnosticsTab } from '../components/studio/tabs/DiagnosticsTab';
import { SettingsTab } from '../components/studio/tabs/SettingsTab';
import {
  Project,
  Repository,
  RepositorySnapshot,
  HealthResponse,
  Integration,
} from '@/lib/api';

const mockProject: Project = {
  id: 'proj-1',
  organization_id: 'org-1',
  name: 'Acme Storefront',
  slug: 'acme-storefront',
  description: 'Production e-commerce storefront',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockIntegration: Integration = {
  id: 'int-1',
  project_id: 'proj-1',
  provider: 'github',
  name: 'Primary GitHub App',
  status: 'ACTIVE',
  configuration: {},
  has_credentials: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockRepo: Repository = {
  id: 'repo-1',
  project_id: 'proj-1',
  integration_id: 'int-1',
  provider: 'github',
  name: 'storefront-web',
  full_name: 'acme/storefront-web',
  external_id: 'gh-12345',
  default_branch: 'main',
  url: 'https://github.com/acme/storefront-web',
  status: 'CONNECTED',
  metadata: {},
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockSnapshot: RepositorySnapshot = {
  id: 'snap-1',
  repository_id: 'repo-1',
  branch: 'main',
  commit_sha: 'abcdef1234567890abcdef1234567890abcdef12',
  status: 'READY',
  metadata: {},
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockHealth: HealthResponse = {
  status: 'healthy',
  service: 'fussion-backend',
  version: '0.1.0',
  database: {
    status: 'connected',
    type: 'postgresql',
    latency_ms: 0.5,
  },
};

describe('Studio Component Suite (Phase B)', () => {
  describe('StudioHeader', () => {
    it('renders branding, project selector, and operational health badge', () => {
      const onSelectProject = vi.fn();
      const onOpenNewProject = vi.fn();
      const onRefreshHealth = vi.fn();

      render(
        <StudioHeader
          projects={[mockProject]}
          selectedProjectId="proj-1"
          onSelectProject={onSelectProject}
          onOpenNewProject={onOpenNewProject}
          health={mockHealth}
          loadingHealth={false}
          onRefreshHealth={onRefreshHealth}
        />
      );

      expect(screen.getByText('Fussion')).toBeDefined();
      expect(screen.getByText('Studio')).toBeDefined();
      expect(screen.getByText('AI Integration Engineer')).toBeDefined();
      expect(screen.getByText('Operational')).toBeDefined();
      expect(screen.getByText('Acme Storefront')).toBeDefined();

      const newBtn = screen.getByTitle('Create new project');
      fireEvent.click(newBtn);
      expect(onOpenNewProject).toHaveBeenCalled();
    });

    it('renders user profile and triggers onLogout when sign out is clicked', () => {
      const onLogout = vi.fn();
      const mockUser = {
        id: 'usr-1',
        email: 'alex@example.com',
        full_name: 'Alex Engineer',
        is_active: true,
        is_superuser: false,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      };

      render(
        <StudioHeader
          projects={[mockProject]}
          selectedProjectId="proj-1"
          onSelectProject={vi.fn()}
          onOpenNewProject={vi.fn()}
          health={mockHealth}
          loadingHealth={false}
          onRefreshHealth={vi.fn()}
          user={mockUser}
          onLogout={onLogout}
        />
      );

      expect(screen.getByText('Alex Engineer')).toBeDefined();
      const signOutBtn = screen.getByTitle('Sign out of your workspace');
      expect(signOutBtn).toBeDefined();

      fireEvent.click(signOutBtn);
      expect(onLogout).toHaveBeenCalled();
    });
  });

  describe('StudioNavigation', () => {
    it('renders all 7 customer journey and system tabs and handles tab switching', () => {
      const onTabChange = vi.fn();
      const { rerender } = render(
        <StudioNavigation activeTab="overview" onTabChange={onTabChange} />
      );

      expect(screen.getByText('Overview')).toBeDefined();
      expect(screen.getByText('Website')).toBeDefined();
      expect(screen.getByText('Knowledge')).toBeDefined();
      expect(screen.getByText('Assistant')).toBeDefined();
      expect(screen.getByText('Integration')).toBeDefined();
      expect(screen.getByText('Diagnostics')).toBeDefined();
      expect(screen.getByText('Settings')).toBeDefined();

      fireEvent.click(screen.getByText('Website'));
      expect(onTabChange).toHaveBeenCalledWith('website');

      fireEvent.click(screen.getByText('Diagnostics'));
      expect(onTabChange).toHaveBeenCalledWith('diagnostics');

      // Re-render with diagnostics active
      rerender(<StudioNavigation activeTab="diagnostics" onTabChange={onTabChange} />);
      const diagBtn = screen.getByText('Diagnostics').closest('button');
      expect(diagBtn?.className).toContain('bg-zinc-800');
    });
  });

  describe('OverviewTab', () => {
    it('renders customer journey progression stepper and status summary cards', () => {
      const onNavigate = vi.fn();

      render(
        <OverviewTab
          project={mockProject}
          repositories={[mockRepo]}
          snapshots={[mockSnapshot]}
          inspectionResult={null}
          onNavigate={onNavigate}
        />
      );

      expect(screen.getByText('Integration Journey')).toBeDefined();
      expect(screen.getByText('Project Setup')).toBeDefined();
      expect(screen.getByText('Website Connected')).toBeDefined();
      expect(screen.getAllByText('Knowledge Base').length).toBeGreaterThan(0);
      expect(screen.getByText('Assistant Design')).toBeDefined();
      expect(screen.getByText('Integration & PR')).toBeDefined();
      expect(screen.getByText('Live Assistant')).toBeDefined();

      expect(screen.getByText('AI Integration Engineer Workspace')).toBeDefined();
      expect(screen.getByText('Manage Website')).toBeDefined();

      fireEvent.click(screen.getByText('Manage Website'));
      expect(onNavigate).toHaveBeenCalledWith('website');
    });
  });

  describe('WebsiteTab', () => {
    it('renders repository card and snapshot details', () => {
      const onOpenNewRepo = vi.fn();
      const onOpenNewIntegration = vi.fn();
      const onOpenAcquireModal = vi.fn();
      const onInspect = vi.fn();

      render(
        <WebsiteTab
          integrations={[mockIntegration]}
          repositories={[mockRepo]}
          snapshots={[mockSnapshot]}
          selectedSnapshotId="snap-1"
          onSelectSnapshot={vi.fn()}
          onOpenNewRepo={onOpenNewRepo}
          onOpenNewIntegration={onOpenNewIntegration}
          onOpenAcquireModal={onOpenAcquireModal}
          inspectionResult={null}
          isInspecting={false}
          onInspect={onInspect}
        />
      );

      expect(screen.getByText('storefront-web')).toBeDefined();
      expect(screen.getByText('acme/storefront-web')).toBeDefined();
      expect(screen.getByText('Website & Repository')).toBeDefined();
      expect(screen.getByText('Snapshot Revision Details')).toBeDefined();
      expect(screen.getByText('Inspect Source')).toBeDefined();
    });
  });

  describe('KnowledgeTab', () => {
    it('renders Phase 09 Knowledge Base grounding engine view', () => {
      render(<KnowledgeTab orgId="org-1" projectId="proj-1" />);

      expect(screen.getByText('Knowledge Base')).toBeDefined();
      expect(screen.getByText('Grounding Engine')).toBeDefined();
      expect(screen.getByText('Upload business knowledge documents')).toBeDefined();
      expect(screen.getByText('Test Knowledge Retrieval')).toBeDefined();
    });
  });

  describe('AssistantTab', () => {
    it('renders assistant configuration controls and preview widget mockup', () => {
      render(<AssistantTab orgId="org-1" projectId="proj-1" />);

      expect(screen.getByText(/Assistant Configuration & Widget Studio/i)).toBeDefined();
      expect(screen.getByText('Phase 10')).toBeDefined();
      expect(screen.getByText(/Appearance & Widget Styling/i)).toBeDefined();
      expect(screen.getByText(/Live Interactive Preview/i)).toBeDefined();
      expect(screen.getByDisplayValue('Fussion Assistant')).toBeDefined();
      expect(screen.getByDisplayValue('Hi! How can I help you today?')).toBeDefined();
    });
  });

  describe('IntegrationTab', () => {
    it('renders website integration pipeline and controls', () => {
      render(<IntegrationTab orgId="demo-org" projectId="demo-proj-1" />);

      expect(screen.getByText(/Automated Website Integration & Pull Request Pipeline/i)).toBeDefined();
      expect(screen.getByText('Phase 11')).toBeDefined();
      expect(screen.getByText(/Repository Connection/i)).toBeDefined();
      expect(screen.getByText(/Integration Status/i)).toBeDefined();
      expect(screen.getByText(/Integration Pipeline Controls/i)).toBeDefined();
    });
  });

  describe('DiagnosticsTab', () => {
    it('renders diagnostic sub-navigation and non-execution architectural view', () => {
      render(
        <DiagnosticsTab
          selectedSnapshotId="snap-1"
          snapshots={[mockSnapshot]}
          discoveries={[]}
          selectedDiscovery={null}
          isRunningDiscovery={false}
          onRunDiscovery={vi.fn()}
          contracts={[]}
          selectedContract={null}
          isNormalizingContract={false}
          onNormalizeContract={vi.fn()}
          integrationPlans={[]}
          selectedPlan={null}
          isGeneratingPlan={false}
          onGeneratePlan={vi.fn()}
          adapters={[]}
          selectedAdapter={null}
          onSelectAdapter={vi.fn()}
          isPlanningAdapters={false}
          onPlanAdapters={vi.fn()}
          executionPlans={[]}
          selectedExecutionPlan={null}
          isGeneratingExecutionPlan={false}
          onGenerateExecutionPlan={vi.fn()}
        />
      );

      expect(screen.getByText(/Technical Details & Engineering Diagnostics/i)).toBeDefined();
      expect(screen.getByText('Post-MVP / Diagnostic Tooling')).toBeDefined();
      expect(screen.getByText('Architecture Discovery')).toBeDefined();
      expect(screen.getByText('API Contracts & Reconciliation')).toBeDefined();
      expect(screen.getByText('Integration Planning & Credentials')).toBeDefined();
      expect(screen.getByText('Adapters & Execution Plans')).toBeDefined();
      expect(screen.getByText('Static Architecture Discovery')).toBeDefined();
      expect(screen.getByText('Run Discovery')).toBeDefined();
    });
  });

  describe('SettingsTab', () => {
    it('renders backend health telemetry and project metadata', () => {
      render(
        <SettingsTab
          health={mockHealth}
          lastChecked="Just now"
          project={mockProject}
        />
      );

      expect(screen.getByText(/Project & System Settings/i)).toBeDefined();
      expect(screen.getByText('Backend Operational Telemetry')).toBeDefined();
      expect(screen.getByText('healthy')).toBeDefined();
      expect(screen.getByText('connected')).toBeDefined();
      expect(screen.getByText('Acme Storefront')).toBeDefined();
      expect(screen.getByText('acme-storefront')).toBeDefined();
      expect(screen.getByText('proj-1')).toBeDefined();
    });
  });
});
