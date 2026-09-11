'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  websiteIntegrationApi,
  WebsiteIntegrationConfig,
  IntegrationRun,
  IntegrationPlanPayload,
  ValidationResultPayload,
  RunDiffPayload,
  PullRequestInfo,
} from '@/lib/api/integration';
import { IntegrationFormState } from '../types';

const DEFAULT_FORM: IntegrationFormState = {
  repository_owner: '',
  repository_name: '',
  default_branch: 'main',
  framework: 'REACT_NEXTJS',
  website_root_dir: '/',
  widget_target_path: 'app/layout.tsx',
  github_token: '',
};

export function useIntegration(orgId?: string, projectId?: string) {
  const [config, setConfig] = useState<WebsiteIntegrationConfig | null>(null);
  const [form, setForm] = useState<IntegrationFormState>(DEFAULT_FORM);
  const [plan, setPlan] = useState<IntegrationPlanPayload | null>(null);
  const [validation, setValidation] = useState<ValidationResultPayload | null>(null);
  const [runs, setRuns] = useState<IntegrationRun[]>([]);
  const [selectedRunDiff, setSelectedRunDiff] = useState<RunDiffPayload | null>(null);
  const [selectedPR, setSelectedPR] = useState<PullRequestInfo | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [isPlanning, setIsPlanning] = useState<boolean>(false);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);

  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!orgId || !projectId) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const cfg = await websiteIntegrationApi.get(orgId, projectId);
      setConfig(cfg);
      setForm({
        repository_owner: cfg.repository_owner,
        repository_name: cfg.repository_name,
        default_branch: cfg.default_branch,
        framework: cfg.framework,
        website_root_dir: cfg.website_root_dir,
        widget_target_path: cfg.widget_target_path,
        github_token: '',
      });

      // Load runs
      try {
        const runList = await websiteIntegrationApi.listRuns(orgId, projectId);
        setRuns(runList);
      } catch {
        // Runs optional
      }
    } catch {
      // 404 indicates not yet configured
      setConfig(null);
      setForm(DEFAULT_FORM);
      setRuns([]);
    } finally {
      setIsLoading(false);
    }
  }, [orgId, projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const updateFormField = useCallback(<K extends keyof IntegrationFormState>(key: K, value: IntegrationFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  const saveConfiguration = useCallback(async () => {
    if (!orgId || !projectId) return;
    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      let updated: WebsiteIntegrationConfig;
      if (!config) {
        updated = await websiteIntegrationApi.create(orgId, projectId, {
          repository_owner: form.repository_owner,
          repository_name: form.repository_name,
          default_branch: form.default_branch,
          framework: form.framework,
          website_root_dir: form.website_root_dir,
          widget_target_path: form.widget_target_path,
          github_token: form.github_token || undefined,
        });
        setSuccessMessage('Website repository connection configured.');
      } else {
        updated = await websiteIntegrationApi.update(orgId, projectId, {
          repository_owner: form.repository_owner,
          repository_name: form.repository_name,
          default_branch: form.default_branch,
          framework: form.framework,
          website_root_dir: form.website_root_dir,
          widget_target_path: form.widget_target_path,
          github_token: form.github_token || undefined,
        });
        setSuccessMessage('Integration configuration updated.');
      }

      setConfig(updated);
      setForm((prev) => ({ ...prev, github_token: '' }));
      // Auto generate plan on save
      try {
        const newPlan = await websiteIntegrationApi.getPlan(orgId, projectId);
        setPlan(newPlan);
      } catch {
        // Plan will be generated on demand
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save integration configuration.');
    } finally {
      setIsSaving(false);
    }
  }, [orgId, projectId, config, form]);

  const validateConnection = useCallback(async () => {
    if (!orgId || !projectId) return;
    setIsValidating(true);
    setError(null);

    try {
      const res = await websiteIntegrationApi.validate(orgId, projectId);
      setValidation(res);
      if (!res.is_valid && res.issues.length > 0) {
        setError(res.issues.join('; '));
      } else {
        setSuccessMessage('Repository connection & branch validation passed.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Repository validation check failed.');
    } finally {
      setIsValidating(false);
    }
  }, [orgId, projectId]);

  const generatePlan = useCallback(async () => {
    if (!orgId || !projectId) return;
    setIsPlanning(true);
    setError(null);

    try {
      const res = await websiteIntegrationApi.getPlan(orgId, projectId);
      setPlan(res);
      setSuccessMessage('Deterministic integration plan generated.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to generate integration plan.');
    } finally {
      setIsPlanning(false);
    }
  }, [orgId, projectId]);

  const executePipelineRun = useCallback(async () => {
    if (!orgId || !projectId) return;
    setIsExecuting(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const newRun = await websiteIntegrationApi.startRun(orgId, projectId);
      setRuns((prev) => [newRun, ...prev.filter((r) => r.id !== newRun.id)]);

      if (newRun.status === 'PR_CREATED') {
        setSuccessMessage(`Pull Request #${newRun.pull_request_number} created successfully!`);
        if (newRun.pull_request_number) {
          setSelectedPR({
            pull_request_number: newRun.pull_request_number,
            pull_request_url: newRun.pull_request_url,
            branch_name: newRun.branch_name,
            base_branch: config?.default_branch || 'main',
            title: 'Integrate Fussion Assistant',
            status: 'open',
          });
        }
      } else {
        setError(newRun.error_message || 'Pipeline finished with non-success status.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to execute integration pipeline.');
    } finally {
      setIsExecuting(false);
    }
  }, [orgId, projectId, config]);

  const viewDiff = useCallback(async (runId: string) => {
    if (!orgId || !projectId) return;
    try {
      const diffData = await websiteIntegrationApi.getRunDiff(orgId, projectId, runId);
      setSelectedRunDiff(diffData);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load run diff.');
    }
  }, [orgId, projectId]);

  const cancelRun = useCallback(async (runId: string) => {
    if (!orgId || !projectId) return;
    try {
      const updated = await websiteIntegrationApi.cancelRun(orgId, projectId, runId);
      setRuns((prev) => prev.map((r) => (r.id === runId ? updated : r)));
      setSuccessMessage('Integration run cancelled.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel run.');
    }
  }, [orgId, projectId]);

  const deleteConfiguration = useCallback(async () => {
    if (!orgId || !projectId) return;
    setIsSaving(true);
    try {
      await websiteIntegrationApi.delete(orgId, projectId);
      setConfig(null);
      setForm(DEFAULT_FORM);
      setPlan(null);
      setValidation(null);
      setRuns([]);
      setSelectedPR(null);
      setSelectedRunDiff(null);
      setSuccessMessage('Website integration deleted.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete integration.');
    } finally {
      setIsSaving(false);
    }
  }, [orgId, projectId]);

  return {
    config,
    form,
    plan,
    validation,
    runs,
    latestRun: runs[0] || null,
    selectedRunDiff,
    selectedPR,
    isLoading,
    isSaving,
    isValidating,
    isPlanning,
    isExecuting,
    error,
    successMessage,
    updateFormField,
    saveConfiguration,
    validateConnection,
    generatePlan,
    executePipelineRun,
    viewDiff,
    cancelRun,
    deleteConfiguration,
    clearSelectedDiff: () => setSelectedRunDiff(null),
    clearSuccess: () => setSuccessMessage(null),
    clearError: () => setError(null),
  };
}
