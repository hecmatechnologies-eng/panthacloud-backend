'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Project, Organization, organizationsApi, projectsApi, getToken } from '@/lib/api';
import { useAuth } from '@/features/auth';
import { useStudioEventStream } from './hooks/useStudioEventStream';
import {
  ProjectContextValue,
  StageId,
  StageStatus,
  ProjectProgress,
  StudioActivityEvent,
  StudioRunStatus,
} from './types';

const defaultFallbackContext: ProjectContextValue = {
  projects: [],
  currentProject: null,
  activeOrg: null,
  isLoading: false,
  error: null,
  isCreateModalOpen: false,
  activeItem: 'overview',
  setActiveItem: () => {},
  openCreateModal: () => {},
  closeCreateModal: () => {},
  selectProject: () => {},
  createProject: async () => {
    throw new Error('ProjectProvider is required to create a project');
  },
  refreshProjects: async () => {},
  isStageCompleted: () => false,
  isStageActionable: () => false,
  getStageStatus: () => 'waiting',
  markStageCompleted: () => {},
  pinnedStageIds: [],
  previewStageId: null,
  studioActivity: [],
  pinStage: () => {},
  unpinStage: () => {},
  setPreviewStageId: () => {},
  getStageRunStatus: () => 'idle',
  recordStageActivity: () => {},
};

const ProjectContext = createContext<ProjectContextValue>(defaultFallbackContext);

export const ProjectProvider: React.FC<{
  children: React.ReactNode;
  initialProjects?: Project[];
  initialCurrentProject?: Project | null;
  initialOrg?: Organization | null;
}> = ({
  children,
  initialProjects = [],
  initialCurrentProject = null,
  initialOrg = null,
}) => {
  const { isAuthenticated } = useAuth();
  const [projects, setProjects] = useState<Project[]>(initialProjects);
  const [currentProject, setCurrentProject] = useState<Project | null>(initialCurrentProject);
  const [activeOrg, setActiveOrg] = useState<Organization | null>(
    initialOrg ||
      (initialCurrentProject
        ? {
            id: initialCurrentProject.organization_id,
            name: 'Organization',
            slug: 'org',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }
        : null)
  );
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [activeItem, setActiveItem] = useState<StageId>('overview');
  const [projectProgress, setProjectProgress] = useState<Record<string, ProjectProgress>>({});
  const [pinnedStages, setPinnedStages] = useState<Record<string, StageId[]>>({});
  const [previewStageId, setPreviewStageId] = useState<StageId | null>(null);
  const [activityByProject, setActivityByProject] = useState<Record<string, StudioActivityEvent[]>>({});
  const [runStatusByProject, setRunStatusByProject] = useState<Record<string, Partial<Record<StageId, StudioRunStatus>>>>({});
  const currentProjectRef = useRef(currentProject);
  currentProjectRef.current = currentProject;

  const refreshProjects = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const token = getToken() || undefined;
      const orgs = await organizationsApi.list(token);

      if (orgs && orgs.length > 0) {
        const org = orgs[0];
        setActiveOrg(org);

        const projectList = await projectsApi.list(org.id, token);
        setProjects(projectList);

        // If no current project selected, select the first one if available
        setCurrentProject((prev) => {
          if (prev && projectList.some((p) => p.id === prev.id)) {
            return prev;
          }
          return projectList.length > 0 ? projectList[0] : null;
        });
      } else {
        setProjects([]);
        setCurrentProject(null);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load projects');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch initial data on authentication
  useEffect(() => {
    if (isAuthenticated) {
      refreshProjects();
    } else {
      setIsLoading(false);
    }
  }, [isAuthenticated, refreshProjects]);

  const selectProject = useCallback((project: Project | null) => {
    setCurrentProject(project);
    setActiveItem('overview');
    setPreviewStageId(null);
    if (project?.organization_id) {
      setActiveOrg((prev) => {
        if (prev?.id === project.organization_id) return prev;
        return {
          id: project.organization_id,
          name: prev?.name || 'Organization',
          slug: prev?.slug || 'org',
          created_at: prev?.created_at || new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
      });
    }
  }, []);

  const recordStageActivity = useCallback(
    ({ stageId, status, message }: Omit<StudioActivityEvent, 'id' | 'createdAt'>) => {
      const project = currentProjectRef.current;
      if (!project) return;

      const event: StudioActivityEvent = {
        id: `${project.id}-${stageId}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        stageId,
        status,
        message,
        createdAt: new Date().toISOString(),
      };
      setActivityByProject((previous) => ({
        ...previous,
        [project.id]: [event, ...(previous[project.id] || [])].slice(0, 40),
      }));
      setRunStatusByProject((previous) => ({
        ...previous,
        [project.id]: { ...(previous[project.id] || {}), [stageId]: status },
      }));
    },
    []
  );

  const pinStage = useCallback((stage: StageId) => {
    const project = currentProjectRef.current;
    if (!project || stage === 'overview') return;
    setPinnedStages((previous) => {
      const current = previous[project.id] || [];
      if (current.includes(stage)) return previous;
      return { ...previous, [project.id]: [...current, stage] };
    });
    setActiveItem(stage);
  }, []);

  const unpinStage = useCallback((stage: StageId) => {
    const project = currentProjectRef.current;
    if (!project) return;
    setPinnedStages((previous) => ({
      ...previous,
      [project.id]: (previous[project.id] || []).filter((item) => item !== stage),
    }));
  }, []);

  const openCreateModal = useCallback(() => {
    setIsCreateModalOpen(true);
  }, []);

  const closeCreateModal = useCallback(() => {
    setIsCreateModalOpen(false);
  }, []);

  const isStageCompleted = useCallback(
    (stage: StageId): boolean => {
      const proj = currentProjectRef.current;
      if (!proj) return false;
      const prog = projectProgress[proj.id];
      if (!prog) return false;

      switch (stage) {
        case 'website':
          return Boolean(prog.website);
        case 'knowledge':
          return Boolean(prog.knowledge);
        case 'assistant':
          return Boolean(prog.assistant);
        case 'integration':
          return Boolean(prog.integration);
        case 'preview':
          return Boolean(prog.live);
        default:
          return false;
      }
    },
    [projectProgress]
  );

  const isStageActionable = useCallback(
    (stage: StageId): boolean => {
      switch (stage) {
        case 'overview':
        case 'settings':
        case 'website':
          return true;
        case 'knowledge':
          return isStageCompleted('website');
        case 'assistant':
          return isStageCompleted('knowledge');
        case 'integration':
          return isStageCompleted('assistant');
        case 'preview':
          return isStageCompleted('integration');
        case 'activity':
          return isStageCompleted('preview');
        default:
          return true;
      }
    },
    [isStageCompleted]
  );

  const getStageStatus = useCallback(
    (stage: StageId): StageStatus => {
      if (stage === activeItem) return 'current';
      if (isStageCompleted(stage)) return 'completed';
      if (isStageActionable(stage)) return 'actionable';
      return 'waiting';
    },
    [activeItem, isStageCompleted, isStageActionable]
  );

  const markStageCompleted = useCallback(
    (stage: StageId, completed: boolean = true) => {
      const proj = currentProjectRef.current;
      if (!proj) return;
      const key: keyof ProjectProgress | null =
        stage === 'preview'
          ? 'live'
          : stage === 'website' ||
            stage === 'knowledge' ||
            stage === 'assistant' ||
            stage === 'integration'
          ? stage
          : null;

      if (!key) return;
      if (isStageCompleted(stage) === completed) return;

      setProjectProgress((prev) => {
        const current = prev[proj.id] || {
          website: false,
          knowledge: false,
          assistant: false,
          integration: false,
          live: false,
        };
        if (current[key] === completed) {
          return prev;
        }
        return {
          ...prev,
          [proj.id]: {
            ...current,
            [key]: completed,
          },
        };
      });
      recordStageActivity({
        stageId: stage,
        status: completed ? 'success' : 'waiting',
        message: completed ? 'Stage completed successfully.' : 'Stage is ready to be configured again.',
      });
    },
    [isStageCompleted, recordStageActivity]
  );

  const getStageRunStatus = useCallback(
    (stage: StageId): StudioRunStatus => {
      const project = currentProjectRef.current;
      const reportedStatus = project ? runStatusByProject[project.id]?.[stage] : undefined;
      if (reportedStatus === 'failed' || reportedStatus === 'running') return reportedStatus;
      if (isStageCompleted(stage)) return 'success';
      if (reportedStatus) return reportedStatus;
      if (!isStageActionable(stage)) return 'waiting';
      return 'idle';
    },
    [isStageActionable, isStageCompleted, runStatusByProject]
  );

  const pinnedStageIds = currentProject ? pinnedStages[currentProject.id] || [] : [];
  const studioActivity = currentProject ? activityByProject[currentProject.id] || [] : [];

  useStudioEventStream({
    organizationId: activeOrg?.id,
    projectId: currentProject?.id,
    onEvent: recordStageActivity,
  });

  const createProject = useCallback(
    async ({ name, description }: { name: string; description?: string }): Promise<Project> => {
      setError(null);
      const token = getToken() || undefined;

      let orgId = activeOrg?.id;
      if (!orgId) {
        const orgs = await organizationsApi.list(token);
        if (!orgs || orgs.length === 0) {
          throw new Error('No organization found for current user');
        }
        setActiveOrg(orgs[0]);
        orgId = orgs[0].id;
      }

      const newProject = await projectsApi.create(
        orgId,
        {
          name: name.trim(),
          description: description?.trim() || undefined,
        },
        token
      );

      setProjects((prev) => [newProject, ...prev]);
      setCurrentProject(newProject);
      setActiveItem('overview');
      setIsCreateModalOpen(false);

      return newProject;
    },
    [activeOrg]
  );

  const contextValue = useMemo<ProjectContextValue>(
    () => ({
      projects,
      currentProject,
      activeOrg,
      isLoading,
      error,
      isCreateModalOpen,
      activeItem,
      setActiveItem,
      openCreateModal,
      closeCreateModal,
      selectProject,
      createProject,
      refreshProjects,
      isStageCompleted,
      isStageActionable,
      getStageStatus,
      markStageCompleted,
      pinnedStageIds,
      previewStageId,
      studioActivity,
      pinStage,
      unpinStage,
      setPreviewStageId,
      getStageRunStatus,
      recordStageActivity,
    }),
    [
      projects,
      currentProject,
      activeOrg,
      isLoading,
      error,
      isCreateModalOpen,
      activeItem,
      openCreateModal,
      closeCreateModal,
      selectProject,
      createProject,
      refreshProjects,
      isStageCompleted,
      isStageActionable,
      getStageStatus,
      markStageCompleted,
      pinnedStageIds,
      previewStageId,
      studioActivity,
      pinStage,
      unpinStage,
      getStageRunStatus,
      recordStageActivity,
    ]
  );

  return (
    <ProjectContext.Provider value={contextValue}>
      {children}
    </ProjectContext.Provider>
  );
};

export function useProject(): ProjectContextValue {
  return useContext(ProjectContext);
}
