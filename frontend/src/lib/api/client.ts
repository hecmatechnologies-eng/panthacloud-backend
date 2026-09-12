export const TOKEN_STORAGE_KEY = 'fussion_token';
export const USER_STORAGE_KEY = 'fussion_user';

export const getBaseUrl = (): string =>
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USER_STORAGE_KEY);
}

export class ApiClientError extends Error {
  public status: number;
  public code?: string;
  public details?: unknown;

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface RequestOptions extends RequestInit {
  token?: string;
}

/**
 * A validation failure arrives as a list of issues, not a string. Passing the list straight to
 * `new Error(...)` rendered "[object Object]" in the UI, so a carefully worded refusal — for
 * example, why a widget target is a protected path — never reached the user.
 */
function flattenValidationIssues(issues: unknown): string | null {
  if (!Array.isArray(issues) || issues.length === 0) return null;
  const messages = issues
    .map((issue) =>
      typeof issue === 'string'
        ? issue
        : typeof issue === 'object' && issue !== null && 'msg' in issue
          ? String((issue as { msg: unknown }).msg).replace(/^Value error,\s*/, '')
          : null,
    )
    .filter((message): message is string => Boolean(message));
  return messages.length > 0 ? messages.join(' ') : null;
}

function flattenDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail;
  return flattenValidationIssues(detail);
}

export async function fetchApi<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const url = `${getBaseUrl()}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  if (!isFormData && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const authToken = options.token || getToken();
  if (authToken && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorData: any = null;
    try {
      errorData = await response.json();
    } catch {
      // ignore json parse error
    }

    const message =
      flattenDetail(errorData?.detail) ||
      flattenValidationIssues(errorData?.error?.details) ||
      errorData?.error?.message ||
      `Request failed with status ${response.status}`;
    const code = errorData?.error?.code;
    const details = errorData?.error?.details;

    if (response.status === 401 && typeof window !== 'undefined') {
      clearToken();
    }

    throw new ApiClientError(message, response.status, code, details);
  }

  if (response.status === 204) {
    return null as unknown as T;
  }

  return response.json();
}
