import { Project, Organization } from '@/lib/api';

export type StageId =
  | 'overview'
  | 'website'
  | 'knowledge'
  | 'assistant'
  | 'integration'
  | 'preview'
  | 'activity'
  | 'settings';

export type ProjectLifecycleStage = StageId;

export type StageStatus = 'current' | 'completed' | 'actionable' | 'waiting';

export type StudioRunStatus = 'idle' | 'running' | 'success' | 'failed' | 'waiting';

export interface StudioActivityEvent {
  id: string;
  stageId: StageId;
  status: StudioRunStatus;
  message: string;
  createdAt: string;
}

export interface ProjectStageConfig {
  id: StageId;
  section: 'BUILD' | 'CONNECT' | 'LIVE' | 'PROJECT';
  title: string;
  stepNumber?: number;
  prerequisite?: StageId;
  prerequisiteName?: string;
  dependencyTitle?: string;
  dependencyExplanation?: string;
  dependencyStatusLabel?: string;
  whatToDoFirst?: string;
  targetStage?: StageId;
  actionLabel?: string;
}

export interface ProjectProgress {
  website: boolean;
  knowledge: boolean;
  assistant: boolean;
  integration: boolean;
  live: boolean;
}

export interface ProjectContextValue {
  projects: Project[];
  currentProject: Project | null;
  activeOrg: Organization | null;
  isLoading: boolean;
  error: string | null;
  isCreateModalOpen: boolean;
  activeItem: StageId;
  setActiveItem: (item: StageId) => void;
  openCreateModal: () => void;
  closeCreateModal: () => void;
  selectProject: (project: Project | null) => void;
  createProject: (input: { name: string; description?: string }) => Promise<Project>;
  refreshProjects: () => Promise<void>;
  isStageCompleted: (stage: StageId) => boolean;
  isStageActionable: (stage: StageId) => boolean;
  getStageStatus: (stage: StageId) => StageStatus;
  markStageCompleted: (stage: StageId, completed?: boolean) => void;
  pinnedStageIds: StageId[];
  previewStageId: StageId | null;
  studioActivity: StudioActivityEvent[];
  pinStage: (stage: StageId) => void;
  unpinStage: (stage: StageId) => void;
  setPreviewStageId: (stage: StageId | null) => void;
  getStageRunStatus: (stage: StageId) => StudioRunStatus;
  recordStageActivity: (event: Omit<StudioActivityEvent, 'id' | 'createdAt'>) => void;
}
