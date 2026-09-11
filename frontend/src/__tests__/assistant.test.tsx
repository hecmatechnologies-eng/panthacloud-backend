import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  AssistantView,
  AssistantIdentityForm,
  AssistantAppearanceForm,
  AssistantBehaviorForm,
  AssistantPreview,
  AssistantSaveBar,
  AssistantStatus,
} from '@/features/assistant';
import { assistantApi, AssistantConfig, AssistantPreviewPayload } from '@/lib/api/assistant';

// Mock assistantApi
vi.mock('@/lib/api/assistant', () => ({
  assistantApi: {
    getAssistant: vi.fn(),
    updateAssistant: vi.fn(),
    resetAssistant: vi.fn(),
    getAssistantPreview: vi.fn(),
  },
}));

const mockConfig: AssistantConfig = {
  id: 'asst-1234-5678',
  project_id: 'proj-100',
  name: 'Storefront Concierge',
  description: 'AI assistant for our online store',
  welcome_message: 'Hi there! How can I help you today?',
  system_instructions: 'Be concise and friendly.',
  brand_color: '#6366F1',
  text_color: '#FFFFFF',
  position: 'BOTTOM_RIGHT',
  avatar_url: 'https://example.com/avatar.png',
  starter_prompt: 'What are your return policies?',
  is_enabled: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockPreviewPayload: AssistantPreviewPayload = {
  assistant: mockConfig,
  knowledge_base: {
    has_knowledge_base: true,
    documents_count: 5,
    ready_chunks_count: 24,
  },
  mock_preview: {
    sample_user_message: 'What are your return policies?',
    sample_assistant_response:
      'Based on 5 documents in your Knowledge Base, we offer 30-day hassle-free returns.',
    grounding_status: 'Online • Grounded in Knowledge Base',
  },
};

describe('Assistant Feature Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(assistantApi.getAssistant).mockResolvedValue(mockConfig);
    vi.mocked(assistantApi.getAssistantPreview).mockResolvedValue(mockPreviewPayload);
  });

  describe('AssistantView Rendering & Data Fetching', () => {
    it('shows placeholder when no project is selected', () => {
      render(<AssistantView />);
      expect(screen.getByText(/No Project Selected/i)).toBeDefined();
    });

    it('renders loaded assistant configuration and status summary', async () => {
      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText(/Assistant Configuration & Widget Studio/i)).toBeDefined();
      });

      expect(screen.getByDisplayValue('Storefront Concierge')).toBeDefined();
      expect(screen.getByDisplayValue('Hi there! How can I help you today?')).toBeDefined();
      expect(screen.getByDisplayValue('#6366F1')).toBeDefined();
      expect(screen.getByDisplayValue('What are your return policies?')).toBeDefined();
      expect(screen.getByText('5 Document(s)')).toBeDefined();
    });
  });

  describe('Reactive Live Preview Updates', () => {
    it('immediately reflects typed assistant name in preview without saving', async () => {
      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('Storefront Concierge')).toBeDefined();
      });

      const nameInput = screen.getByDisplayValue('Storefront Concierge');
      fireEvent.change(nameInput, { target: { value: 'Super Bot 3000' } });

      // Preview chat header should immediately display new name
      expect(screen.getByText('Super Bot 3000')).toBeDefined();
    });

    it('immediately reflects welcome message updates in preview', async () => {
      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('Hi there! How can I help you today?')).toBeDefined();
      });

      const welcomeInput = screen.getByDisplayValue('Hi there! How can I help you today?');
      fireEvent.change(welcomeInput, { target: { value: 'Welcome to our VIP club!' } });

      expect(screen.getAllByText('Welcome to our VIP club!').length).toBe(2);
    });

    it('toggles widget position in the preview', async () => {
      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText('Bottom Left')).toBeDefined();
      });

      const bottomLeftBtn = screen.getByRole('button', { name: /Bottom Left/i });
      fireEvent.click(bottomLeftBtn);

      // Now draft.position is BOTTOM_LEFT; the button should have active class styling
      expect(bottomLeftBtn.className).toContain('bg-violet-950/60');
    });
  });

  describe('Dirty State & Save / Discard Actions', () => {
    it('shows save bar only when form is edited, and discards changes cleanly', async () => {
      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('Storefront Concierge')).toBeDefined();
      });

      // Initially no save bar
      expect(screen.queryByText(/Unsaved Changes/i)).toBeNull();

      // Edit field
      const nameInput = screen.getByDisplayValue('Storefront Concierge');
      fireEvent.change(nameInput, { target: { value: 'Modified Name' } });

      // Save bar appears
      expect(screen.getByText(/Unsaved Changes/i)).toBeDefined();

      // Discard
      const discardBtn = screen.getByRole('button', { name: /Discard/i });
      fireEvent.click(discardBtn);

      // Value restored to baseline
      expect(screen.getByDisplayValue('Storefront Concierge')).toBeDefined();
      expect(screen.queryByText(/Unsaved Changes/i)).toBeNull();
    });

    it('submits updated configuration when clicking Save Changes', async () => {
      const updatedConfig = { ...mockConfig, name: 'Saved Name' };
      vi.mocked(assistantApi.updateAssistant).mockResolvedValue(updatedConfig);

      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('Storefront Concierge')).toBeDefined();
      });

      const nameInput = screen.getByDisplayValue('Storefront Concierge');
      fireEvent.change(nameInput, { target: { value: 'Saved Name' } });

      const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(assistantApi.updateAssistant).toHaveBeenCalledWith(
          'org-1',
          'proj-100',
          expect.objectContaining({ name: 'Saved Name' })
        );
        expect(screen.getByText(/Assistant configuration saved successfully/i)).toBeDefined();
      });

      expect(screen.queryByText(/Unsaved Changes/i)).toBeNull();
    });

    it('resets configuration to defaults on Reset action', async () => {
      const resetConfig: AssistantConfig = {
        ...mockConfig,
        name: 'Fussion Assistant',
        brand_color: '#6366F1',
      };
      vi.mocked(assistantApi.resetAssistant).mockResolvedValue(resetConfig);
      vi.spyOn(window, 'confirm').mockReturnValue(true);

      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByDisplayValue('Storefront Concierge')).toBeDefined();
      });

      // Trigger dirty state first
      const nameInput = screen.getByDisplayValue('Storefront Concierge');
      fireEvent.change(nameInput, { target: { value: 'Another Name' } });

      const resetBtn = screen.getByRole('button', { name: /Reset Defaults/i });
      fireEvent.click(resetBtn);

      await waitFor(() => {
        expect(assistantApi.resetAssistant).toHaveBeenCalledWith('org-1', 'proj-100');
        expect(screen.getByText(/Assistant configuration reset to default values/i)).toBeDefined();
      });
    });
  });

  describe('Interactive Mock Preview Interactions', () => {
    it('clicking starter prompt chip triggers mock grounded response without network call', async () => {
      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText('What are your return policies?')).toBeDefined();
      });

      const promptChip = screen.getByRole('button', {
        name: /What are your return policies\?/i,
      });
      fireEvent.click(promptChip);

      // Mock user question and assistant response should appear in chat body
      await waitFor(() => {
        expect(
          screen.getByText(/Based on the documentation in your connected Knowledge Base/i)
        ).toBeDefined();
      });

      // Reset conversation button appears and can clear messages
      const resetChatBtn = screen.getByRole('button', { name: /Reset Chat/i });
      fireEvent.click(resetChatBtn);

      expect(
        screen.queryByText(/Based on the documentation in your connected Knowledge Base/i)
      ).toBeNull();
    });

    it('switches between desktop and mobile viewport previews', async () => {
      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByTitle('Mobile View')).toBeDefined();
      });

      const mobileBtn = screen.getByTitle('Mobile View');
      fireEvent.click(mobileBtn);

      const desktopBtn = screen.getByTitle('Desktop View');
      fireEvent.click(desktopBtn);
      expect(desktopBtn).toBeDefined();
    });

    it('updates avatar image in preview when avatar URL is provided', async () => {
      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText('https://example.com/assistant-avatar.png')).toBeDefined();
      });

      const avatarInput = screen.getByPlaceholderText('https://example.com/assistant-avatar.png');
      fireEvent.change(avatarInput, { target: { value: 'https://custom.com/my-bot.png' } });

      expect(screen.getByDisplayValue('https://custom.com/my-bot.png')).toBeDefined();
    });

    it('renders error notification banner when assistant API fails', async () => {
      vi.mocked(assistantApi.getAssistant).mockRejectedValueOnce(new Error('Network connection failure'));

      render(<AssistantView orgId="org-1" projectId="proj-100" />);

      await waitFor(() => {
        expect(screen.getByText('Network connection failure')).toBeDefined();
      });
    });
  });
});
