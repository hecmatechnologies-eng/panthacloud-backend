'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import {
  authApi,
  getToken,
  setToken,
  clearToken,
  User,
  USER_STORAGE_KEY,
} from '@/lib/api';
import { AuthContextType, LoginCredentials, SignupCredentials } from './types';

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Hydrate session on mount
  useEffect(() => {
    let isMounted = true;

    async function initializeAuth() {
      try {
        const storedToken = getToken();
        if (!storedToken) {
          if (isMounted) {
            setUser(null);
            setTokenState(null);
            setIsLoading(false);
          }
          return;
        }

        if (isMounted) {
          setTokenState(storedToken);
          // Optimistically load cached user from localStorage if present
          try {
            const cachedUserStr = localStorage.getItem(USER_STORAGE_KEY);
            if (cachedUserStr) {
              setUser(JSON.parse(cachedUserStr));
            }
          } catch {
            // ignore JSON parse errors
          }
        }

        // Validate token with backend /auth/me
        try {
          const remoteUser = await authApi.getMe(storedToken);
          if (isMounted) {
            setUser(remoteUser);
            if (typeof window !== 'undefined') {
              localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(remoteUser));
            }
          }
        } catch (err: any) {
          // If token is rejected (401), clear session
          if (err?.status === 401) {
            clearToken();
            if (isMounted) {
              setUser(null);
              setTokenState(null);
            }
          }
          // Note: if backend is unreachable (network error), keep cached token/user
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    initializeAuth();

    return () => {
      isMounted = false;
    };
  }, []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    setError(null);
    try {
      const response = await authApi.login(credentials);
      setToken(response.access_token);
      if (typeof window !== 'undefined') {
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(response.user));
      }
      setTokenState(response.access_token);
      setUser(response.user);
    } catch (err: any) {
      const msg = err?.message || 'Failed to sign in. Please check your credentials.';
      setError(msg);
      throw err;
    }
  }, []);

  const signup = useCallback(async (credentials: SignupCredentials) => {
    setError(null);
    try {
      const response = await authApi.register(credentials);
      setToken(response.access_token);
      if (typeof window !== 'undefined') {
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(response.user));
      }
      setTokenState(response.access_token);
      setUser(response.user);
    } catch (err: any) {
      const msg = err?.message || 'Failed to create account. Please try again.';
      setError(msg);
      throw err;
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    setTokenState(null);
    setError(null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const value: AuthContextType = {
    user,
    token,
    isAuthenticated: !!token && !!user,
    isLoading,
    error,
    login,
    signup,
    logout,
    clearError,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
