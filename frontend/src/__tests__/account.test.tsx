import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  UserAvatar,
  extractInitials,
  AccountIdentity,
  AccountTrigger,
  AccountMenu,
} from '@/components/account';
import { ThemeProvider } from '@/components/theme';
import { User } from '@/lib/api';

describe('extractInitials utility', () => {
  it('extracts two-letter initials from single word', () => {
    expect(extractInitials('Fussion')).toBe('FU');
  });

  it('extracts first and last initials from multi-word names', () => {
    expect(extractInitials('Alex Morgan')).toBe('AM');
    expect(extractInitials('Jane Sarah Doe')).toBe('JD');
  });

  it('extracts first letter from email address', () => {
    expect(extractInitials('user@example.com')).toBe('U');
  });

  it('returns empty string for null or empty input', () => {
    expect(extractInitials(null)).toBe('');
    expect(extractInitials('')).toBe('');
    expect(extractInitials(undefined)).toBe('');
  });
});

describe('UserAvatar Component', () => {
  it('renders image when avatarUrl is provided (State A)', () => {
    render(
      <UserAvatar
        avatarUrl="https://example.com/avatar.png"
        displayName="Alex Doe"
      />
    );

    const imgTag = screen.getByRole('img');
    expect(imgTag).toBeDefined();
    expect(imgTag.getAttribute('src')).toBe('https://example.com/avatar.png');
  });

  it('falls back to initials when image errors (State A -> State B fallback)', () => {
    render(
      <UserAvatar
        avatarUrl="https://invalid.url/missing.png"
        displayName="Alex Doe"
      />
    );

    const imgTag = screen.getByRole('img');
    expect(imgTag).toBeDefined();
    fireEvent.error(imgTag);

    // Should now show initials "AD"
    expect(screen.getByText('AD')).toBeDefined();
  });

  it('renders initials when name is provided without avatarUrl (State B)', () => {
    const mockUser: User = {
      id: 'usr-1',
      email: 'alex@example.com',
      full_name: 'Alex Morgan',
      is_active: true,
      is_superuser: false,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    render(<UserAvatar user={mockUser} />);
    expect(screen.getByText('AM')).toBeDefined();
  });

  it('renders initial from email when full_name is absent', () => {
    const mockUser: User = {
      id: 'usr-2',
      email: 'developer@example.com',
      full_name: null,
      is_active: true,
      is_superuser: false,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    render(<UserAvatar user={mockUser} />);
    expect(screen.getByText('D')).toBeDefined();
  });

  it('renders generic icon fallback when no identifiers exist (State C)', () => {
    render(<UserAvatar user={null} />);
    const avatar = screen.getByRole('img');
    expect(avatar).toBeDefined();
    expect(avatar.querySelector('svg')).not.toBeNull();
  });

  it('applies size classes correctly', () => {
    const { rerender } = render(<UserAvatar displayName="Test User" size="sm" />);
    expect(screen.getByRole('img').className).toContain('w-8 h-8');

    rerender(<UserAvatar displayName="Test User" size="md" />);
    expect(screen.getByRole('img').className).toContain('w-10 h-10');

    rerender(<UserAvatar displayName="Test User" size="lg" />);
    expect(screen.getByRole('img').className).toContain('w-16 h-16');
  });
});

describe('AccountIdentity Component', () => {
  const baseUser: User = {
    id: 'usr-123',
    email: 'engineer@fussion.internal',
    full_name: 'Lead Engineer',
    is_active: true,
    is_superuser: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };

  it('renders user display name and email in dropdown header', () => {
    render(<AccountIdentity user={baseUser} />);

    expect(screen.getByText('Lead Engineer')).toBeDefined();
    expect(screen.getByText('engineer@fussion.internal')).toBeDefined();
  });
});

describe('AccountTrigger & AccountMenu Components', () => {
  const mockUser: User = {
    id: 'usr-456',
    email: 'admin@fussion.dev',
    full_name: 'Abel Byamukama',
    is_active: true,
    is_superuser: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };

  beforeEach(() => {
    localStorage.clear();
  });

  it('renders pure circular avatar trigger and toggles menu on click', () => {
    render(
      <ThemeProvider>
        <AccountTrigger user={mockUser} />
      </ThemeProvider>
    );

    const button = screen.getByTestId('account-menu-button');
    expect(button.getAttribute('aria-expanded')).toBe('false');
    // Button contains the initials avatar 'AB' without text label 'Account'
    expect(screen.getByText('AB')).toBeDefined();
    expect(screen.queryByText('Account')).toBeNull();
    expect(screen.queryByTestId('account-dropdown')).toBeNull();

    // Open menu
    fireEvent.click(button);
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByTestId('account-dropdown')).toBeDefined();

    // Close menu
    fireEvent.click(button);
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByTestId('account-dropdown')).toBeNull();
  });

  it('closes menu when Escape key is pressed', () => {
    render(
      <ThemeProvider>
        <AccountTrigger user={mockUser} />
      </ThemeProvider>
    );

    const button = screen.getByTestId('account-menu-button');
    fireEvent.click(button);
    expect(screen.getByTestId('account-dropdown')).toBeDefined();

    // Press Escape
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('account-dropdown')).toBeNull();
  });

  it('closes menu when clicking outside', () => {
    render(
      <ThemeProvider>
        <div>
          <div data-testid="outside-element">Outside</div>
          <AccountTrigger user={mockUser} />
        </div>
      </ThemeProvider>
    );

    const button = screen.getByTestId('account-menu-button');
    fireEvent.click(button);
    expect(screen.getByTestId('account-dropdown')).toBeDefined();

    // Click outside
    fireEvent.mouseDown(screen.getByTestId('outside-element'));
    expect(screen.queryByTestId('account-dropdown')).toBeNull();
  });

  it('calls onLogout callback when Sign out is clicked in menu', () => {
    const mockLogout = vi.fn();
    render(
      <ThemeProvider>
        <AccountTrigger user={mockUser} onLogout={mockLogout} />
      </ThemeProvider>
    );

    const button = screen.getByTestId('account-menu-button');
    fireEvent.click(button);

    const signOutBtn = screen.getByTestId('sign-out-button');
    fireEvent.click(signOutBtn);

    expect(mockLogout).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('account-dropdown')).toBeNull();
  });

  it('renders Profile, Account settings, and Appearance with side popup', () => {
    render(
      <ThemeProvider defaultTheme="dark">
        <AccountMenu user={mockUser} isOpen={true} onClose={() => {}} />
      </ThemeProvider>
    );

    expect(screen.getByText('Profile')).toBeDefined();
    expect(screen.getByText('Account settings')).toBeDefined();
    expect(screen.getByText('Appearance')).toBeDefined();

    // Trigger side popup
    const appearanceToggle = screen.getByTestId('appearance-toggle');
    fireEvent.click(appearanceToggle);

    expect(screen.getByTestId('appearance-side-popup')).toBeDefined();
    expect(screen.getByTestId('theme-option-light')).toBeDefined();
    expect(screen.getByTestId('theme-option-dark')).toBeDefined();
    expect(screen.getByTestId('theme-option-system')).toBeDefined();
  });
});
