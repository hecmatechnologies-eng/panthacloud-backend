'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  websiteIntegrationApi,
  WebsiteIntegrationConfig,
  WebsiteIntegrationCreateInput,
  WebsiteAnalysis,
} from '@/lib/api/integration';
import { githubApi, GitHubInstallationRead, GitHubRepositoryRead } from '@/lib/api/github';

export interface UseWebsiteStageProps {
  orgId?: string;
  projectId?: string;
  onStatusChange?: (isCompleted: boolean) => void;
}

export function useWebsiteStage({
  orgId,
  projectId,
  onStatusChange,
}: UseWebsiteStageProps = {}) {
  const [config, setConfig] = useState<WebsiteIntegrationConfig | null>(null);
  const [analysis, setAnalysis] = useState<WebsiteAnalysis | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [isDisconnecting, setIsDisconnecting] = useState<boolean>(false);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [isSelecting, setIsSelecting] = useState<boolean>(false);
  const [installations, setInstallations] = useState<GitHubInstallationRead[]>([]);
  const [repositories, setRepositories] = useState<GitHubRepositoryRead[]>([]);
  const [isLoadingRepositories, setIsLoadingRepositories] = useState<boolean>(false);
  const [isConnectingGitHub, setIsConnectingGitHub] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  // Track last reported status to avoid duplicate updates and eliminate loop feedback
  const lastStatusRef = useRef<boolean | null>(null);

  const notifyStatus = useCallback((connected: boolean) => {
    if (lastStatusRef.current !== connected) {
      lastStatusRef.current = connected;
      onStatusChangeRef.current?.(connected);
    }
  }, []);

  const loadGitHub = useCallback(async () => {
    if (!orgId) return;
    try {
      const installs = await githubApi.installations(orgId);
      setInstallations(installs);
      if (installs.length > 0) {
        setIsLoadingRepositories(true);
        try {
          const list = await githubApi.repositories(orgId, undefined, 1, 100);
          setRepositories(list.repositories);
        } catch {
          setRepositories([]);
        } finally {
          setIsLoadingRepositories(false);
        }
      } else {
        setRepositories([]);
      }
    } catch {
      setInstallations([]);
      setRepositories([]);
    }
  }, [orgId]);

  const loadConfig = useCallback(async () => {
    if (!orgId || !projectId) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    void loadGitHub();

    try {
      const data = await websiteIntegrationApi.get(orgId, projectId);
      setConfig(data);
      const isConnected = data?.status === 'CONNECTED';
      notifyStatus(isConnected);
      try {
        const latestAnalysis = await websiteIntegrationApi.getLatestAnalysis(orgId, projectId);
        setAnalysis(latestAnalysis);
      } catch {
        setAnalysis(null);
      }
    } catch {
      // 404 is normal for projects with no website yet
      setConfig(null);
      setAnalysis(null);
      notifyStatus(false);
    } finally {
      setIsLoading(false);
    }
  }, [orgId, projectId, notifyStatus, loadGitHub]);

  useEffect(() => {
    let isCancelled = false;

    if (!orgId || !projectId) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    void loadGitHub();

    const load = async () => {
      try {
        const data = await websiteIntegrationApi.get(orgId, projectId);
        if (isCancelled) return;
        setConfig(data);
        notifyStatus(data?.status === 'CONNECTED');
        try {
          const latestAnalysis = await websiteIntegrationApi.getLatestAnalysis(orgId, projectId);
          if (!isCancelled) setAnalysis(latestAnalysis);
        } catch {
          if (!isCancelled) setAnalysis(null);
        }
      } catch {
        if (!isCancelled) {
          setConfig(null);
          setAnalysis(null);
          notifyStatus(false);
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    load();

    return () => {
      isCancelled = true;
    };
  }, [orgId, projectId, notifyStatus, loadGitHub]);

  const connect = useCallback(
    async (input: WebsiteIntegrationCreateInput): Promise<WebsiteIntegrationConfig> => {
      if (!orgId || !projectId) {
        throw new Error('Active organization and project are required to connect a website.');
      }

      setIsConnecting(true);
      setError(null);

      try {
        const created = await websiteIntegrationApi.create(orgId, projectId, input);
        setConfig(created);
        notifyStatus(true);
        return created;
      } catch (err: any) {
        const msg = err?.message || 'Failed to connect website repository.';
        setError(msg);
        throw err;
      } finally {
        setIsConnecting(false);
      }
    },
    [orgId, projectId, notifyStatus]
  );

  const disconnect = useCallback(async (): Promise<void> => {
    if (!orgId || !projectId) return;

    setIsDisconnecting(true);
    setError(null);

    try {
      await websiteIntegrationApi.delete(orgId, projectId);
      setConfig(null);
      setAnalysis(null);
      notifyStatus(false);
    } catch (err: any) {
      const msg = err?.message || 'Failed to disconnect website.';
      setError(msg);
      throw err;
    } finally {
      setIsDisconnecting(false);
    }
  }, [orgId, projectId, notifyStatus]);

  const analyze = useCallback(async (): Promise<WebsiteAnalysis> => {
    if (!orgId || !projectId) {
      throw new Error('Active organization and project are required to analyse a website.');
    }

    setIsAnalyzing(true);
    setError(null);

    try {
      const result = await websiteIntegrationApi.analyze(orgId, projectId);
      setAnalysis(result);
      return result;
    } catch (err: any) {
      const msg = err?.message || 'Failed to analyse the repository.';
      setError(msg);
      throw err;
    } finally {
      setIsAnalyzing(false);
    }
  }, [orgId, projectId]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const startGitHubInstall = useCallback(async (): Promise<string> => {
    if (!orgId) {
      throw new Error('An active organization is required to connect GitHub.');
    }
    setIsConnectingGitHub(true);
    setError(null);
    try {
      const { url } = await githubApi.installUrl(orgId);
      return url;
    } catch (err: any) {
      setError(err?.message || 'Failed to start the GitHub connection.');
      throw err;
    } finally {
      setIsConnectingGitHub(false);
    }
  }, [orgId]);

  const connectRepository = useCallback(
    async (repo: GitHubRepositoryRead): Promise<WebsiteIntegrationConfig> =>
      connect({
        repository_owner: repo.owner ?? repo.full_name.split('/')[0],
        repository_name: repo.name,
        default_branch: repo.default_branch,
        github_installation_id: repo.installation_id,
      }),
    [connect]
  );

  const selectTarget = useCallback(
    async (widgetTargetPath: string, frameworkSkillId: string | null): Promise<WebsiteIntegrationConfig> => {
      if (!orgId || !projectId) {
        throw new Error('Active organization and project are required to select a target.');
      }

      setIsSelecting(true);
      setError(null);

      try {
        const updated = await websiteIntegrationApi.update(orgId, projectId, {
          widget_target_path: widgetTargetPath,
          ...(frameworkSkillId ? { framework_skill_id: frameworkSkillId } : {}),
        });
        setConfig(updated);
        return updated;
      } catch (err: any) {
        const msg = err?.message || 'Failed to select the integration point.';
        setError(msg);
        throw err;
      } finally {
        setIsSelecting(false);
      }
    },
    [orgId, projectId]
  );

  return {
    config,
    analysis,
    installations,
    repositories,
    isLoading,
    isConnecting,
    isDisconnecting,
    isAnalyzing,
    isSelecting,
    isLoadingRepositories,
    isConnectingGitHub,
    error,
    connect,
    disconnect,
    analyze,
    selectTarget,
    startGitHubInstall,
    connectRepository,
    refresh: loadConfig,
    clearError,
  };
}
