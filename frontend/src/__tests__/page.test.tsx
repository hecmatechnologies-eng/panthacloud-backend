import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import HomePage from '../app/page';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  fetchHealth: vi.fn(),
}));

describe('HomePage Component', () => {
  it('renders Fussion Phase 01 headers and operational status', async () => {
    vi.mocked(api.fetchHealth).mockResolvedValueOnce({
      status: 'healthy',
      service: 'fussion-backend',
      version: '0.1.0',
      database: {
        status: 'connected',
        type: 'postgresql',
      },
    });

    render(<HomePage />);

    expect(screen.getByText('Fussion')).toBeDefined();
    expect(screen.getByText('Phase 01')).toBeDefined();
    expect(screen.getByText('Frontend')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText('Operational')).toBeDefined();
    });
  });
});
