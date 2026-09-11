import { getBaseUrl } from './client';

export interface DatabaseHealth {
  status: 'connected' | 'disconnected';
  type?: string;
  latency_ms?: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment?: string;
  database?: DatabaseHealth;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${getBaseUrl()}/health`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Backend health check responded with status: ${res.status}`);
  }
  return res.json();
}
