'use client';

import React, { useState } from 'react';
import {
  Bot,
  Laptop,
  MessageSquare,
  RefreshCw,
  Send,
  Smartphone,
  Sparkles,
  X,
} from 'lucide-react';
import { AssistantFormState, PreviewViewport } from '../types';
import { AssistantPreviewPayload } from '@/lib/api/assistant';

interface AssistantPreviewProps {
  draft: AssistantFormState;
  previewPayload: AssistantPreviewPayload | null;
}

interface MockMessage {
  id: string;
  sender: 'assistant' | 'user';
  text: string;
  timestamp: string;
  isGrounded?: boolean;
}

export const AssistantPreview: React.FC<AssistantPreviewProps> = ({
  draft,
  previewPayload,
}) => {
  const [viewport, setViewport] = useState<PreviewViewport>('desktop');
  const [isOpen, setIsOpen] = useState<boolean>(true);
  const [customMessages, setCustomMessages] = useState<MockMessage[]>([]);
  const [hasClickedPrompt, setHasClickedPrompt] = useState<boolean>(false);
  const [avatarError, setAvatarError] = useState<boolean>(false);

  const hasKnowledgeBase = previewPayload?.knowledge_base?.has_knowledge_base ?? false;
  const docsCount = previewPayload?.knowledge_base?.documents_count ?? 0;

  const handleStarterPromptClick = () => {
    if (hasClickedPrompt || !draft.starter_prompt) return;

    const userMsg: MockMessage = {
      id: 'mock-user-1',
      sender: 'user',
      text: draft.starter_prompt,
      timestamp: 'Just now',
    };

    const asstRespText = hasKnowledgeBase
      ? `Hello! Based on the documentation in your connected Knowledge Base, I can confirm the details regarding "${draft.starter_prompt}". This is a preview simulation demonstrating how your assistant answers customer questions.`
      : `Hello! I can help you with "${draft.starter_prompt}". To enable verified factual answers based on your store's policies and products, upload your documentation in the Knowledge Base tab.`;

    const asstMsg: MockMessage = {
      id: 'mock-asst-1',
      sender: 'assistant',
      text: asstRespText,
      timestamp: 'Just now',
      isGrounded: hasKnowledgeBase,
    };

    setCustomMessages([userMsg, asstMsg]);
    setHasClickedPrompt(true);
  };

  const handleResetChat = () => {
    setCustomMessages([]);
    setHasClickedPrompt(false);
  };

  const isLeft = draft.position === 'BOTTOM_LEFT';

  return (
    <div className="space-y-3">
      {/* Top Bar: Preview controls & Viewport Toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[var(--text-primary)] uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-[var(--color-purple)]" />
            Live Interactive Preview
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[var(--surface-elevated)] text-[var(--text-muted)] border border-[var(--border)]">
            Mock Simulation
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Reset Conversation Button */}
          {customMessages.length > 0 && (
            <button
              type="button"
              onClick={handleResetChat}
              className="text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] flex items-center gap-1 bg-[var(--surface-elevated)] px-2 py-1 rounded-lg border border-[var(--border)] transition-colors cursor-pointer"
              title="Reset mock conversation"
            >
              <RefreshCw className="w-3 h-3" />
              <span>Reset Chat</span>
            </button>
          )}

          {/* Viewport Toggles */}
          <div className="flex items-center p-0.5 bg-[var(--surface)] border border-[var(--border)] rounded-xl">
            <button
              type="button"
              onClick={() => setViewport('desktop')}
              className={`p-1.5 rounded-lg text-xs transition-colors flex items-center gap-1 cursor-pointer ${
                viewport === 'desktop'
                  ? 'bg-[var(--surface-elevated)] text-[var(--text-primary)] shadow-xs font-semibold'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
              title="Desktop View"
            >
              <Laptop className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setViewport('mobile')}
              className={`p-1.5 rounded-lg text-xs transition-colors flex items-center gap-1 cursor-pointer ${
                viewport === 'mobile'
                  ? 'bg-[var(--surface-elevated)] text-[var(--text-primary)] shadow-xs font-semibold'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
              title="Mobile View"
            >
              <Smartphone className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Preview Frame Container */}
      <div
        className={`mx-auto bg-zinc-950 border border-[var(--border)] rounded-2xl shadow-2xl relative overflow-hidden transition-all duration-300 ${
          viewport === 'desktop' ? 'w-full h-[540px]' : 'w-[340px] h-[580px]'
        }`}
      >
        {/* Mock Browser Top Header Bar */}
        <div className="bg-zinc-900/90 border-b border-zinc-800 px-3.5 py-2 flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
          </div>
          <div className="flex-1 max-w-[200px] mx-auto bg-zinc-950/80 border border-zinc-800/80 rounded px-2.5 py-0.5 text-[10px] text-zinc-500 text-center font-mono truncate">
            https://your-storefront.com
          </div>
        </div>

        {/* Mock Website Canvas Backdrop */}
        <div className="p-5 h-[calc(100%-37px)] overflow-hidden relative select-none">
          {/* Subtle grid pattern */}
          <div className="absolute inset-0 bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:16px_16px] opacity-30 pointer-events-none" />

          {/* Mock Website Elements */}
          <div className="space-y-4 max-w-md opacity-35 pointer-events-none">
            <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
              <div className="h-4 w-24 bg-zinc-700 rounded" />
              <div className="flex gap-2">
                <div className="h-3 w-12 bg-zinc-800 rounded" />
                <div className="h-3 w-12 bg-zinc-800 rounded" />
              </div>
            </div>
            <div className="space-y-2 pt-2">
              <div className="h-6 w-48 bg-zinc-700 rounded" />
              <div className="h-3 w-64 bg-zinc-800 rounded" />
              <div className="h-3 w-56 bg-zinc-800 rounded" />
            </div>
            <div className="grid grid-cols-2 gap-3 pt-2">
              <div className="h-20 bg-zinc-900 border border-zinc-800 rounded-xl" />
              <div className="h-20 bg-zinc-900 border border-zinc-800 rounded-xl" />
            </div>
          </div>

          {/* Interactive Chat Popup Window */}
          {isOpen && (
            <div
              className={`absolute bottom-16 z-30 w-[300px] sm:w-[320px] bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col transition-all duration-200 ${
                isLeft ? 'left-4' : 'right-4'
              }`}
              style={{ maxHeight: '420px' }}
            >
              {/* Chat Header */}
              <div
                style={{
                  backgroundColor: draft.brand_color,
                  color: draft.text_color,
                }}
                className="p-3.5 flex items-center justify-between shadow-md transition-colors"
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center overflow-hidden shrink-0">
                    {draft.avatar_url && !avatarError ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={draft.avatar_url}
                        alt="Avatar"
                        onError={() => setAvatarError(true)}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <Bot className="w-4 h-4" />
                    )}
                  </div>
                  <div>
                    <h3 className="font-bold text-xs leading-tight line-clamp-1">
                      {draft.name || 'Fussion Assistant'}
                    </h3>
                    <div className="flex items-center gap-1.5 text-[10px] opacity-90">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block animate-pulse" />
                      <span>
                        {hasKnowledgeBase
                          ? `Grounded (${docsCount} docs)`
                          : 'Preview Mode'}
                      </span>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="p-1 rounded-lg hover:bg-black/20 transition-colors"
                  title="Close chat"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Chat Scrollable Content */}
              <div className="p-3.5 space-y-3 bg-zinc-950 text-xs overflow-y-auto max-h-[260px] min-h-[180px]">
                {/* Assistant Welcome Greeting */}
                <div className="flex items-start gap-2 max-w-[90%]">
                  <div className="w-6 h-6 rounded-full bg-zinc-800 flex items-center justify-center shrink-0 mt-0.5 text-zinc-300">
                    <Bot className="w-3.5 h-3.5" />
                  </div>
                  <div className="bg-zinc-900 border border-zinc-800/80 rounded-2xl rounded-tl-none p-3 text-zinc-200 shadow-sm">
                    <p className="leading-relaxed">
                      {draft.welcome_message || 'Hi! How can I help you today?'}
                    </p>
                  </div>
                </div>

                {/* Suggested Starter Prompt Chip */}
                {draft.starter_prompt && !hasClickedPrompt && (
                  <div className="pt-1">
                    <span className="text-[10px] text-zinc-400 block mb-1 font-medium">
                      Suggested question:
                    </span>
                    <button
                      type="button"
                      onClick={handleStarterPromptClick}
                      className="group bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-800 hover:border-violet-500/50 text-zinc-300 hover:text-white rounded-full px-3 py-1.5 text-[11px] text-left transition-all flex items-center gap-1.5 shadow-sm"
                    >
                      <MessageSquare className="w-3 h-3 text-violet-400 group-hover:scale-110 transition-transform" />
                      <span className="line-clamp-1">{draft.starter_prompt}</span>
                    </button>
                  </div>
                )}

                {/* Custom Mock Conversation Messages */}
                {customMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex items-start gap-2 ${
                      msg.sender === 'user'
                        ? 'justify-end ml-auto max-w-[85%]'
                        : 'justify-start max-w-[90%]'
                    }`}
                  >
                    {msg.sender === 'assistant' && (
                      <div className="w-6 h-6 rounded-full bg-zinc-800 flex items-center justify-center shrink-0 mt-0.5 text-zinc-300">
                        <Bot className="w-3.5 h-3.5" />
                      </div>
                    )}
                    <div
                      className={`rounded-2xl p-3 text-xs leading-relaxed ${
                        msg.sender === 'user'
                          ? 'bg-violet-600 text-white rounded-tr-none'
                          : 'bg-zinc-900 border border-zinc-800/80 text-zinc-200 rounded-tl-none'
                      }`}
                    >
                      <p>{msg.text}</p>
                      {msg.isGrounded && (
                        <span className="inline-flex items-center gap-1 text-[9px] text-emerald-400 mt-1 font-medium">
                          <span className="w-1 h-1 rounded-full bg-emerald-400" />
                          Grounded in Knowledge Base
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Chat Input Bar */}
              <div className="p-2.5 bg-zinc-900 border-t border-zinc-800 flex items-center gap-2">
                <input
                  type="text"
                  disabled
                  placeholder="Ask a question..."
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-1.5 text-xs text-zinc-400 placeholder-zinc-500 focus:outline-none"
                />
                <button
                  type="button"
                  disabled
                  style={{
                    backgroundColor: draft.brand_color,
                    color: draft.text_color,
                  }}
                  className="p-1.5 rounded-xl shadow shrink-0 opacity-80"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* Floating Assistant Launcher Button */}
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            style={{
              backgroundColor: draft.brand_color,
              color: draft.text_color,
            }}
            className={`absolute bottom-4 z-40 w-11 h-11 rounded-full shadow-2xl flex items-center justify-center transition-all duration-200 hover:scale-110 active:scale-95 ${
              isLeft ? 'left-4' : 'right-4'
            }`}
            title={isOpen ? 'Collapse assistant widget' : 'Open assistant widget'}
          >
            {isOpen ? (
              <X className="w-5 h-5" />
            ) : draft.avatar_url && !avatarError ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={draft.avatar_url}
                alt="Avatar"
                onError={() => setAvatarError(true)}
                className="w-full h-full rounded-full object-cover"
              />
            ) : (
              <Bot className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
