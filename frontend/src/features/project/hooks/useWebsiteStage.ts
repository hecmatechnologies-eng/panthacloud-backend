'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  websiteIntegrationApi,
  WebsiteIntegrationConfig,
  WebsiteIntegrationCreateInput,
  WebsiteAnalysis,
} from '@/lib/api/integration';

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

  const loadConfig = useCallback(async () => {
    if (!orgId || !projectId) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

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
  }, [orgId, projectId, notifyStatus]);

  useEffect(() => {
    let isCancelled = false;

    if (!orgId || !projectId) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

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
  }, [orgId, projectId, notifyStatus]);

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

  return {
    config,
    analysis,
    isLoading,
    isConnecting,
    isDisconnecting,
    isAnalyzing,
    error,
    connect,
    disconnect,
    analyze,
    refresh: loadConfig,
    clearError,
  };
}
