import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { assistantApi, AssistantConfig, AssistantPreviewPayload } from '@/lib/api/assistant';
import { AssistantFormState, AssistantReadinessState } from '../types';

export interface UseAssistantOptions {
  onStatusChange?: (isCompleted: boolean, readiness: AssistantReadinessState) => void;
  isKnowledgeGrounded?: boolean;
}

const DEFAULT_FORM_STATE: AssistantFormState = {
  name: 'Fussion Assistant',
  description: '',
  welcome_message: 'Hi! How can I help you today?',
  starter_prompt: 'What can you tell me about your products?',
  brand_color: '#6366F1',
  text_color: '#FFFFFF',
  position: 'BOTTOM_RIGHT',
  avatar_url: '',
  is_enabled: true,
  system_instructions: '',
};

function configToFormState(config: AssistantConfig): AssistantFormState {
  return {
    name: config.name || 'Fussion Assistant',
    description: config.description || '',
    welcome_message: config.welcome_message || 'Hi! How can I help you today?',
    starter_prompt: config.starter_prompt || 'What can you tell me about your products?',
    brand_color: config.brand_color || '#6366F1',
    text_color: config.text_color || '#FFFFFF',
    position: config.position || 'BOTTOM_RIGHT',
    avatar_url: config.avatar_url || '',
    is_enabled: config.is_enabled ?? true,
    system_instructions: config.system_instructions || '',
  };
}

export function useAssistant(
  orgId?: string,
  projectId?: string,
  options?: UseAssistantOptions
) {
  const [config, setConfig] = useState<AssistantConfig | null>(null);
  const [previewPayload, setPreviewPayload] = useState<AssistantPreviewPayload | null>(null);
  const [baseline, setBaseline] = useState<AssistantFormState | null>(null);
  const [draft, setDraft] = useState<AssistantFormState>(DEFAULT_FORM_STATE);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Compute dirty state by deep comparing draft vs baseline
  const isDirty = useMemo(() => {
    if (!baseline) return false;
    return (
      draft.name !== baseline.name ||
      draft.description !== baseline.description ||
      draft.welcome_message !== baseline.welcome_message ||
      draft.starter_prompt !== baseline.starter_prompt ||
      draft.brand_color !== baseline.brand_color ||
      draft.text_color !== baseline.text_color ||
      draft.position !== baseline.position ||
      draft.avatar_url !== baseline.avatar_url ||
      draft.is_enabled !== baseline.is_enabled ||
      draft.system_instructions !== baseline.system_instructions
    );
  }, [draft, baseline]);

  const loadAssistant = useCallback(async () => {
    if (!orgId || !projectId) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const [asstData, previewData] = await Promise.all([
        assistantApi.getAssistant(orgId, projectId),
        assistantApi.getAssistantPreview(orgId, projectId).catch(() => null),
      ]);

      setConfig(asstData);
      const formState = configToFormState(asstData);
      setBaseline(formState);
      setDraft(formState);
      if (previewData) {
        setPreviewPayload(previewData);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load assistant configuration.');
    } finally {
      setIsLoading(false);
    }
  }, [orgId, projectId]);

  useEffect(() => {
    loadAssistant();
  }, [loadAssistant]);

  const updateField = useCallback(
    <K extends keyof AssistantFormState>(field: K, value: AssistantFormState[K]) => {
      setDraft((prev) => ({ ...prev, [field]: value }));
      if (success) setSuccess(null);
    },
    [success]
  );

  const save = useCallback(async () => {
    if (!orgId || !projectId) return;

    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const updated = await assistantApi.updateAssistant(orgId, projectId, {
        name: draft.name.trim(),
        description: draft.description ? draft.description.trim() : null,
        welcome_message: draft.welcome_message.trim(),
        starter_prompt: draft.starter_prompt ? draft.starter_prompt.trim() : null,
        brand_color: draft.brand_color,
        text_color: draft.text_color,
        position: draft.position,
        avatar_url: draft.avatar_url ? draft.avatar_url.trim() : null,
        is_enabled: draft.is_enabled,
        system_instructions: draft.system_instructions ? draft.system_instructions.trim() : null,
      });

      setConfig(updated);
      const newFormState = configToFormState(updated);
      setBaseline(newFormState);
      setDraft(newFormState);
      setSuccess('Assistant configuration saved successfully.');

      // Refresh preview payload in background
      assistantApi.getAssistantPreview(orgId, projectId).then(setPreviewPayload).catch(() => {});
    } catch (err: any) {
      setError(err?.message || 'Failed to save assistant configuration.');
    } finally {
      setIsSaving(false);
    }
  }, [orgId, projectId, draft]);

  const discard = useCallback(() => {
    if (baseline) {
      setDraft(baseline);
      setError(null);
      setSuccess(null);
    }
  }, [baseline]);

  const reset = useCallback(async () => {
    if (!orgId || !projectId) return;

    setIsResetting(true);
    setError(null);
    setSuccess(null);

    try {
      const resetConfig = await assistantApi.resetAssistant(orgId, projectId);
      setConfig(resetConfig);
      const newFormState = configToFormState(resetConfig);
      setBaseline(newFormState);
      setDraft(newFormState);
      setSuccess('Assistant configuration reset to default values.');

      assistantApi.getAssistantPreview(orgId, projectId).then(setPreviewPayload).catch(() => {});
    } catch (err: any) {
      setError(err?.message || 'Failed to reset assistant configuration.');
    } finally {
      setIsResetting(false);
    }
  }, [orgId, projectId]);

  // 1. Configured: Persisted record exists with required identity fields
  const isConfigured = Boolean(
    config &&
    config.id &&
    config.name?.trim().length >= 1 &&
    config.welcome_message?.trim().length >= 1
  );

  // 2. Grounded: Knowledge base connected and documents available
  const isGrounded = Boolean(
    options?.isKnowledgeGrounded !== undefined
      ? options.isKnowledgeGrounded
      : previewPayload?.knowledge_base?.has_knowledge_base ?? false
  );

  // 3. System Readiness Assertion:
  // - draft: dirty edits pending
  // - configured: saved to DB, but knowledge grounding missing
  // - configured_grounded / ready_for_integration: both saved & grounded
  const readinessState: AssistantReadinessState = useMemo(() => {
    if (isDirty) return 'draft';
    if (!isConfigured) return 'draft';
    if (!isGrounded) return 'configured';
    return 'ready_for_integration';
  }, [isDirty, isConfigured, isGrounded]);

  const isCompleted = readinessState === 'ready_for_integration';

  // Deduplicate status notifications to prevent re-render loops
  const lastNotifiedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!options?.onStatusChange) return;
    const key = `${readinessState}:${isCompleted}`;
    if (lastNotifiedRef.current !== key) {
      lastNotifiedRef.current = key;
      options.onStatusChange(isCompleted, readinessState);
    }
  }, [readinessState, isCompleted, options]);

  return {
    config,
    previewPayload,
    draft,
    baseline,
    isLoading,
    isSaving,
    isResetting,
    isDirty,
    error,
    success,
    readinessState,
    isCompleted,
    isConfigured,
    isGrounded,
    updateField,
    save,
    discard,
    reset,
    reload: loadAssistant,
  };
}
