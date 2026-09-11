import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  AuthProvider,
  useAuth,
  LoginForm,
  SignupForm,
  ProtectedRoute,
} from '@/features/auth';
import * as authApiModule from '@/lib/api/auth';
import * as clientModule from '@/lib/api/client';
import RootPage from '@/app/page';
import { mockPush, mockReplace } from '../../vitest.setup';

const mockUser = {
  id: 'user-123',
  email: 'dev@example.com',
  full_name: 'Alex Developer',
  is_active: true,
  is_superuser: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('Phase B.1 Authentication Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('LoginForm', () => {
    it('renders login form with all inputs and links', () => {
      render(
        <AuthProvider>
          <LoginForm />
        </AuthProvider>
      );

      expect(screen.getByText('Fussion')).toBeDefined();
      expect(screen.getByText('Welcome back')).toBeDefined();
      expect(screen.getByPlaceholderText('developer@example.com')).toBeDefined();
      expect(screen.getByPlaceholderText('••••••••')).toBeDefined();
      expect(screen.getByRole('button', { name: /Sign In/i })).toBeDefined();
      expect(screen.getByText(/Don't have an account\?/i)).toBeDefined();
    });

    it('validates required email and password', async () => {
      render(
        <AuthProvider>
          <LoginForm />
        </AuthProvider>
      );

      const submitBtn = screen.getByRole('button', { name: /Sign In/i });
      fireEvent.click(submitBtn);

      expect(screen.getByText('Please enter your email address.')).toBeDefined();

      const emailInput = screen.getByPlaceholderText('developer@example.com');
      fireEvent.change(emailInput, { target: { value: 'dev@example.com' } });
      fireEvent.click(submitBtn);

      expect(screen.getByText('Please enter your password.')).toBeDefined();
    });

    it('submits valid credentials and navigates to /studio', async () => {
      const loginSpy = vi.spyOn(authApiModule.authApi, 'login').mockResolvedValueOnce({
        access_token: 'mock-jwt-token',
        token_type: 'bearer',
        user: mockUser,
      });

      render(
        <AuthProvider>
          <LoginForm />
        </AuthProvider>
      );

      fireEvent.change(screen.getByPlaceholderText('developer@example.com'), {
        target: { value: 'dev@example.com' },
      });
      fireEvent.change(screen.getByPlaceholderText('••••••••'), {
        target: { value: 'secret123' },
      });

      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

      await waitFor(() => {
        expect(loginSpy).toHaveBeenCalledWith({
          email: 'dev@example.com',
          password: 'secret123',
        });
        expect(mockPush).toHaveBeenCalledWith('/studio');
      });
    });

    it('handles invalid credentials with error message banner', async () => {
      vi.spyOn(authApiModule.authApi, 'login').mockRejectedValueOnce(
        new clientModule.ApiClientError('Invalid email or password.', 401)
      );

      render(
        <AuthProvider>
          <LoginForm />
        </AuthProvider>
      );

      fireEvent.change(screen.getByPlaceholderText('developer@example.com'), {
        target: { value: 'wrong@example.com' },
      });
      fireEvent.change(screen.getByPlaceholderText('••••••••'), {
        target: { value: 'wrongpass' },
      });

      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

      await waitFor(() => {
        expect(screen.getByText('Invalid email or password.')).toBeDefined();
      });
    });

    it('handles network error during login gracefully', async () => {
      vi.spyOn(authApiModule.authApi, 'login').mockRejectedValueOnce(
        new Error('Network error: Unable to connect to backend')
      );

      render(
        <AuthProvider>
          <LoginForm />
        </AuthProvider>
      );

      fireEvent.change(screen.getByPlaceholderText('developer@example.com'), {
        target: { value: 'dev@example.com' },
      });
      fireEvent.change(screen.getByPlaceholderText('••••••••'), {
        target: { value: 'password123' },
      });

      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

      await waitFor(() => {
        expect(
          screen.getByText('Network error: Unable to connect to backend')
        ).toBeDefined();
      });
    });
  });

  describe('SignupForm', () => {
    it('renders signup form with fields and validation', () => {
      render(
        <AuthProvider>
          <SignupForm />
        </AuthProvider>
      );

      expect(screen.getByText('Create your workspace')).toBeDefined();
      expect(screen.getByPlaceholderText('developer@example.com')).toBeDefined();
      expect(screen.getByPlaceholderText('Jane Doe')).toBeDefined();
      expect(screen.getByPlaceholderText('Acme Inc.')).toBeDefined();
      expect(screen.getByPlaceholderText('Min 8 characters')).toBeDefined();
      expect(screen.getByPlaceholderText('Repeat password')).toBeDefined();
      expect(screen.getByRole('button', { name: /Create Account/i })).toBeDefined();
      expect(screen.getByText(/Already have an account\?/i)).toBeDefined();
    });

    it('validates email format and password length/match', async () => {
      render(
        <AuthProvider>
          <SignupForm />
        </AuthProvider>
      );

      const submitBtn = screen.getByRole('button', { name: /Create Account/i });
      fireEvent.click(submitBtn);
      expect(screen.getByText('Please enter your email address.')).toBeDefined();

      fireEvent.change(screen.getByPlaceholderText('developer@example.com'), {
        target: { value: 'invalid-email' },
      });
      fireEvent.click(submitBtn);
      expect(screen.getByText('Please enter a valid email address.')).toBeDefined();

      fireEvent.change(screen.getByPlaceholderText('developer@example.com'), {
        target: { value: 'valid@example.com' },
      });
      fireEvent.click(submitBtn);
      expect(screen.getByText('Please enter a password.')).toBeDefined();

      fireEvent.change(screen.getByPlaceholderText('Min 8 characters'), {
        target: { value: 'short' },
      });
      fireEvent.click(submitBtn);
      expect(screen.getByText('Password must be at least 8 characters long.')).toBeDefined();

      fireEvent.change(screen.getByPlaceholderText('Min 8 characters'), {
        target: { value: 'password123' },
      });
      fireEvent.change(screen.getByPlaceholderText('Repeat password'), {
        target: { value: 'different123' },
      });
      fireEvent.click(submitBtn);
      expect(screen.getByText('Passwords do not match.')).toBeDefined();
    });

    it('submits valid registration and navigates to /studio', async () => {
      const registerSpy = vi.spyOn(authApiModule.authApi, 'register').mockResolvedValueOnce({
        access_token: 'new-jwt-token',
        token_type: 'bearer',
        user: mockUser,
      });

      render(
        <AuthProvider>
          <SignupForm />
        </AuthProvider>
      );

      fireEvent.change(screen.getByPlaceholderText('Jane Doe'), {
        target: { value: 'Alex Developer' },
      });
      fireEvent.change(screen.getByPlaceholderText('developer@example.com'), {
        target: { value: 'alex@company.com' },
      });
      fireEvent.change(screen.getByPlaceholderText('Acme Inc.'), {
        target: { value: 'Alex Org' },
      });
      fireEvent.change(screen.getByPlaceholderText('Min 8 characters'), {
        target: { value: 'securePass123' },
      });
      fireEvent.change(screen.getByPlaceholderText('Repeat password'), {
        target: { value: 'securePass123' },
      });

      fireEvent.click(screen.getByRole('button', { name: /Create Account/i }));

      await waitFor(() => {
        expect(registerSpy).toHaveBeenCalledWith({
          email: 'alex@company.com',
          password: 'securePass123',
          full_name: 'Alex Developer',
          org_name: 'Alex Org',
        });
        expect(mockPush).toHaveBeenCalledWith('/studio');
      });
    });

    it('handles duplicate registration failure with error banner', async () => {
      vi.spyOn(authApiModule.authApi, 'register').mockRejectedValueOnce(
        new clientModule.ApiClientError(
          'A user with this email address already exists.',
          400
        )
      );

      render(
        <AuthProvider>
          <SignupForm />
        </AuthProvider>
      );

      fireEvent.change(screen.getByPlaceholderText('developer@example.com'), {
        target: { value: 'existing@example.com' },
      });
      fireEvent.change(screen.getByPlaceholderText('Min 8 characters'), {
        target: { value: 'password123' },
      });
      fireEvent.change(screen.getByPlaceholderText('Repeat password'), {
        target: { value: 'password123' },
      });

      fireEvent.click(screen.getByRole('button', { name: /Create Account/i }));

      await waitFor(() => {
        expect(
          screen.getByText('A user with this email address already exists.')
        ).toBeDefined();
      });
    });
  });

  describe('AuthProvider & useAuth', () => {
    const TestConsumer: React.FC = () => {
      const { user, token, isAuthenticated, isLoading, logout } = useAuth();
      return (
        <div>
          <span data-testid="auth-loading">{isLoading ? 'loading' : 'ready'}</span>
          <span data-testid="auth-status">
            {isAuthenticated ? 'authenticated' : 'unauthenticated'}
          </span>
          <span data-testid="auth-user">{user?.email || 'none'}</span>
          <span data-testid="auth-token">{token || 'none'}</span>
          <button onClick={logout}>Logout</button>
        </div>
      );
    };

    it('initializes as unauthenticated when no stored token exists', async () => {
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-loading').textContent).toBe('ready');
        expect(screen.getByTestId('auth-status').textContent).toBe('unauthenticated');
        expect(screen.getByTestId('auth-user').textContent).toBe('none');
        expect(screen.getByTestId('auth-token').textContent).toBe('none');
      });
    });

    it('restores authenticated user when a valid stored token exists', async () => {
      localStorage.setItem('fussion_token', 'valid-token-123');
      vi.spyOn(authApiModule.authApi, 'getMe').mockResolvedValueOnce(mockUser);

      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-loading').textContent).toBe('ready');
        expect(screen.getByTestId('auth-status').textContent).toBe('authenticated');
        expect(screen.getByTestId('auth-user').textContent).toBe('dev@example.com');
        expect(screen.getByTestId('auth-token').textContent).toBe('valid-token-123');
      });
    });

    it('clears invalid token on 401 response and remains unauthenticated', async () => {
      localStorage.setItem('fussion_token', 'expired-token');
      vi.spyOn(authApiModule.authApi, 'getMe').mockRejectedValueOnce(
        new clientModule.ApiClientError('Unauthorized', 401)
      );

      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-loading').textContent).toBe('ready');
        expect(screen.getByTestId('auth-status').textContent).toBe('unauthenticated');
        expect(localStorage.getItem('fussion_token')).toBeNull();
      });
    });

    it('clears authentication state on logout', async () => {
      localStorage.setItem('fussion_token', 'token-to-logout');
      vi.spyOn(authApiModule.authApi, 'getMe').mockResolvedValueOnce(mockUser);

      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status').textContent).toBe('authenticated');
      });

      fireEvent.click(screen.getByRole('button', { name: /Logout/i }));

      expect(screen.getByTestId('auth-status').textContent).toBe('unauthenticated');
      expect(screen.getByTestId('auth-token').textContent).toBe('none');
      expect(localStorage.getItem('fussion_token')).toBeNull();
    });
  });

  describe('ProtectedRoute', () => {
    it('redirects unauthenticated users to /login and does not render children', async () => {
      render(
        <AuthProvider>
          <ProtectedRoute>
            <div>Protected Secret Content</div>
          </ProtectedRoute>
        </AuthProvider>
      );

      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith('/login');
        expect(screen.queryByText('Protected Secret Content')).toBeNull();
      });
    });

    it('renders protected children when authenticated', async () => {
      localStorage.setItem('fussion_token', 'valid-token');
      vi.spyOn(authApiModule.authApi, 'getMe').mockResolvedValueOnce(mockUser);

      render(
        <AuthProvider>
          <ProtectedRoute>
            <div>Protected Secret Content</div>
          </ProtectedRoute>
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByText('Protected Secret Content')).toBeDefined();
      });
    });
  });

  describe('Root Page Router', () => {
    it('redirects unauthenticated visitors to /login', async () => {
      render(
        <AuthProvider>
          <RootPage />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith('/login');
      });
    });

    it('redirects authenticated visitors to /studio', async () => {
      localStorage.setItem('fussion_token', 'valid-token');
      vi.spyOn(authApiModule.authApi, 'getMe').mockResolvedValueOnce(mockUser);

      render(
        <AuthProvider>
          <RootPage />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith('/studio');
      });
    });
  });
});
