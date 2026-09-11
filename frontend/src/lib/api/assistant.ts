import { fetchApi } from './client';

export type AssistantPosition = 'BOTTOM_RIGHT' | 'BOTTOM_LEFT';

export interface AssistantConfig {
  id: string;
  project_id: string;
  name: string;
  description?: string | null;
  welcome_message: string;
  system_instructions?: string | null;
  brand_color: string;
  text_color: string;
  position: AssistantPosition;
  avatar_url?: string | null;
  starter_prompt?: string | null;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AssistantUpdateInput {
  name?: string;
  description?: string | null;
  welcome_message?: string;
  system_instructions?: string | null;
  brand_color?: string;
  text_color?: string;
  position?: AssistantPosition;
  avatar_url?: string | null;
  starter_prompt?: string | null;
  is_enabled?: boolean;
}

export interface AssistantPreviewPayload {
  assistant: AssistantConfig;
  knowledge_base: {
    has_knowledge_base: boolean;
    documents_count: number;
    ready_chunks_count: number;
  };
  mock_preview: {
    sample_user_message: string;
    sample_assistant_response: string;
    grounding_status: string;
  };
}

export const assistantApi = {
  getAssistant: async (orgId: string, projectId: string): Promise<AssistantConfig> => {
    return fetchApi<AssistantConfig>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/assistant`
    );
  },

  updateAssistant: async (
    orgId: string,
    projectId: string,
    data: AssistantUpdateInput
  ): Promise<AssistantConfig> => {
    return fetchApi<AssistantConfig>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/assistant`,
      {
        method: 'PATCH',
        body: JSON.stringify(data),
      }
    );
  },

  resetAssistant: async (orgId: string, projectId: string): Promise<AssistantConfig> => {
    return fetchApi<AssistantConfig>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/assistant/reset`,
      {
        method: 'POST',
      }
    );
  },

  getAssistantPreview: async (
    orgId: string,
    projectId: string
  ): Promise<AssistantPreviewPayload> => {
    return fetchApi<AssistantPreviewPayload>(
      `/api/v1/organizations/${orgId}/projects/${projectId}/assistant/preview`
    );
  },
};
