'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  websiteIntegrationApi,
  WebsiteIntegrationConfig,
  WebsiteIntegrationCreateInput,
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
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [isDisconnecting, setIsDisconnecting] = useState<boolean>(false);
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
    } catch {
      // 404 is normal for projects with no website yet
      setConfig(null);
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

    websiteIntegrationApi
      .get(orgId, projectId)
      .then((data) => {
        if (!isCancelled) {
          setConfig(data);
          const isConnected = data?.status === 'CONNECTED';
          notifyStatus(isConnected);
        }
      })
      .catch(() => {
        if (!isCancelled) {
          setConfig(null);
          notifyStatus(false);
        }
      })
      .finally(() => {
        if (!isCancelled) {
          setIsLoading(false);
        }
      });

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
      notifyStatus(false);
    } catch (err: any) {
      const msg = err?.message || 'Failed to disconnect website.';
      setError(msg);
      throw err;
    } finally {
      setIsDisconnecting(false);
    }
  }, [orgId, projectId, notifyStatus]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    config,
    isLoading,
    isConnecting,
    isDisconnecting,
    error,
    connect,
    disconnect,
    refresh: loadConfig,
    clearError,
  };
}
