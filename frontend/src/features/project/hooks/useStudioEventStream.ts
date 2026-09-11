'use client';

import { useEffect, useRef } from 'react';
import { getBaseUrl, getToken } from '@/lib/api';
import { StageId, StudioRunStatus } from '../types';

interface ServerStudioEvent {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

const getStage = (eventType: string): StageId => {
  if (eventType.startsWith('knowledge.')) return 'knowledge';
  if (eventType.startsWith('assistant.')) return 'assistant';
  if (eventType.startsWith('integration.run') || eventType.includes('pull_request')) return 'integration';
  if (eventType.startsWith('integration.')) return 'website';
  return 'activity';
};

const getStatus = (eventType: string): StudioRunStatus => {
  if (/(failed|error|cancelled)/.test(eventType)) return 'failed';
  if (/(processed|validated|completed|created|updated)/.test(eventType)) return 'success';
  if (/(started|running|ingestion)/.test(eventType)) return 'running';
  return 'idle';
};

const getMessage = (eventType: string, payload: Record<string, unknown>) => {
  const repository = typeof payload.repository === 'string' ? ` for ${payload.repository}` : '';
  const messages: Record<string, string> = {
    'integration.created': `Website connection saved${repository}.`,
    'integration.updated': `Website connection updated${repository}.`,
    'integration.deleted': 'Website connection removed.',
    'integration.run.started': 'Integration run started.',
    'integration.run.validated': 'Integration checks passed.',
    'integration.pull_request.created': 'Pull request is ready for review.',
    'knowledge.document.processed': 'Knowledge document is ready to use.',
    'assistant.updated': 'Assistant configuration saved.',
  };
  return messages[eventType] || eventType.replaceAll('.', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
};

export const useStudioEventStream = ({
  organizationId,
  projectId,
  onEvent,
}: {
  organizationId?: string;
  projectId?: string;
  onEvent: (event: { stageId: StageId; status: StudioRunStatus; message: string }) => void;
}) => {
  const onEventRef = useRef(onEvent);
  const seenIds = useRef(new Set<string>());

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!organizationId || !projectId) return;
    const token = getToken();
    if (!token) return;

    const controller = new AbortController();
    const connect = async () => {
      try {
        const response = await fetch(
          `${getBaseUrl()}/api/v1/organizations/${organizationId}/projects/${projectId}/events/stream`,
          { headers: { Accept: 'text/event-stream', Authorization: `Bearer ${token}` }, signal: controller.signal }
        );
        if (!response.ok || !response.body) return;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const messages = buffer.split('\n\n');
          buffer = messages.pop() || '';
          messages.forEach((message) => {
            const dataLine = message.split('\n').find((line) => line.startsWith('data: '));
            if (!dataLine) return;
            try {
              const event = JSON.parse(dataLine.slice(6)) as ServerStudioEvent;
              if (seenIds.current.has(event.id)) return;
              seenIds.current.add(event.id);
              onEventRef.current({
                stageId: getStage(event.event_type),
                status: getStatus(event.event_type),
                message: getMessage(event.event_type, event.payload || {}),
              });
            } catch {
              // Ignore malformed stream messages and keep the studio connected.
            }
          });
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          // The next project change reconnects; action-level feedback remains available meanwhile.
        }
      }
    };
    void connect();
    return () => controller.abort();
  }, [organizationId, projectId]);
};
