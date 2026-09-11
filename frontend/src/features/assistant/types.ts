import { AssistantConfig, AssistantPosition, AssistantPreviewPayload } from '@/lib/api/assistant';

export type PreviewViewport = 'desktop' | 'mobile';

export type AssistantReadinessState =
  | 'draft'
  | 'configured'
  | 'configured_grounded'
  | 'ready_for_integration';

export interface AssistantFormState {
  name: string;
  description: string;
  welcome_message: string;
  starter_prompt: string;
  brand_color: string;
  text_color: string;
  position: AssistantPosition;
  avatar_url: string;
  is_enabled: boolean;
  system_instructions: string;
}

export interface AssistantViewState {
  config: AssistantConfig | null;
  draft: AssistantFormState;
  baseline: AssistantFormState | null;
  isLoading: boolean;
  isSaving: boolean;
  isResetting: boolean;
  isDirty: boolean;
  error: string | null;
  success: string | null;
  previewPayload: AssistantPreviewPayload | null;
}
