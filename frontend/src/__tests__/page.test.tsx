import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import StudioPage from '../app/(app)/studio/page';
import { AppShell } from '@/components/layout';
import { AuthProvider } from '@/features/auth';
import { ThemeProvider } from '@/components/theme';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

describe('Authenticated Studio Shell & Visual Canvas', () => {
  it('renders application shell with Fussion branding, circular Account affordance, technical canvas environment, and studio hero', () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <AppShell>
            <StudioPage />
          </AppShell>
        </AuthProvider>
      </ThemeProvider>
    );

    // Branding & Header
    expect(screen.getByText('Fussion')).toBeDefined();
    expect(screen.getByTestId('studio-header')).toBeDefined();
    expect(screen.getByTestId('account-menu-button')).toBeDefined();

    // Canvas environment
    expect(screen.getByTestId('studio-canvas')).toBeDefined();
    expect(screen.getByTestId('canvas-background-layer')).toBeDefined();
    expect(screen.getByTestId('canvas-grid-layer')).toBeDefined();

    // Studio workspace & Welcome hero
    expect(screen.getByTestId('studio-workspace')).toBeDefined();
    expect(screen.getByTestId('empty-workspace')).toBeDefined();
    expect(screen.getByText('Welcome to Fussion')).toBeDefined();
    expect(screen.getByText(/Your workspace for building powerful AI assistants/i)).toBeDefined();
    expect(screen.getByText(/Build.*Connect.*Automate.*Live/i)).toBeDefined();
    expect(screen.getByTestId('studio-status-badge')).toBeDefined();
  });

  it('does NOT mount feature tabs, navigation, or modals in the empty shell', () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <AppShell>
            <StudioPage />
          </AppShell>
        </AuthProvider>
      </ThemeProvider>
    );

    // Feature tabs must remain disconnected
    expect(screen.queryByText('Knowledge Base Foundation')).toBeNull();
    expect(screen.queryByText(/Assistant Configuration & Widget Studio/i)).toBeNull();
    expect(screen.queryByText(/Automated Website Integration/i)).toBeNull();
    expect(screen.queryByText(/Integration Delivery Pipeline/i)).toBeNull();
    expect(screen.queryByText(/Architecture Discovery/i)).toBeNull();
    expect(screen.queryByText(/Project & System Settings/i)).toBeNull();
  });

  it('opens account dropdown on click and displays user profile and sign out action', async () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <AppShell>
            <StudioPage />
          </AppShell>
        </AuthProvider>
      </ThemeProvider>
    );

    const accountBtn = screen.getByTestId('account-menu-button');
    fireEvent.click(accountBtn);

    expect(screen.getByTestId('account-dropdown')).toBeDefined();
    expect(screen.getByTestId('sign-out-button')).toBeDefined();

    const signOutBtn = screen.getByTestId('sign-out-button');
    fireEvent.click(signOutBtn);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/login');
    });
  });

  it('renders StudioPage in isolation with empty-workspace test ID and hero text', () => {
    render(<StudioPage />);
    expect(screen.getByTestId('empty-workspace')).toBeDefined();
    expect(screen.getByText('Welcome to Fussion')).toBeDefined();
  });
});
