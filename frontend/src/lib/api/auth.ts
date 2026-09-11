import { fetchApi } from './client';

export interface UserProfile {
  displayName?: string;
  avatarUrl?: string | null;
  preferences?: Record<string, unknown>;
}

export type AuthProviderType = 'password' | 'google' | 'github';

export interface AuthIdentity {
  provider: AuthProviderType;
  providerEmail?: string;
  providerUserId?: string;
  metadata?: Record<string, unknown>;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  profile?: UserProfile;
  identities?: AuthIdentity[];
  created_at: string;
  updated_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
  org_name?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export const authApi = {
  async login(payload: LoginRequest): Promise<TokenResponse> {
    return fetchApi<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async register(payload: RegisterRequest): Promise<TokenResponse> {
    return fetchApi<TokenResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getMe(token?: string): Promise<User> {
    return fetchApi<User>('/api/v1/auth/me', {
      method: 'GET',
      token,
      cache: 'no-store',
    });
  },
};
