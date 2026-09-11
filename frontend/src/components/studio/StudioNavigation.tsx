'use client';

import React from 'react';
import {
  LayoutDashboard,
  Globe,
  BookOpen,
  Bot,
  GitPullRequest,
  Activity,
  Settings,
} from 'lucide-react';

export type StudioTabId =
  | 'overview'
  | 'website'
  | 'knowledge'
  | 'assistant'
  | 'integration'
  | 'diagnostics'
  | 'settings';

interface StudioNavigationProps {
  activeTab: StudioTabId;
  onTabChange: (tab: StudioTabId) => void;
}

export const StudioNavigation: React.FC<StudioNavigationProps> = ({
  activeTab,
  onTabChange,
}) => {
  const journeyTabs = [
    { id: 'overview' as StudioTabId, label: 'Overview', icon: LayoutDashboard },
    { id: 'website' as StudioTabId, label: 'Website', icon: Globe },
    { id: 'knowledge' as StudioTabId, label: 'Knowledge', icon: BookOpen },
    { id: 'assistant' as StudioTabId, label: 'Assistant', icon: Bot },
    { id: 'integration' as StudioTabId, label: 'Integration', icon: GitPullRequest },
  ];

  const secondaryTabs = [
    { id: 'diagnostics' as StudioTabId, label: 'Diagnostics', icon: Activity },
    { id: 'settings' as StudioTabId, label: 'Settings', icon: Settings },
  ];

  return (
    <div className="border-b border-zinc-800/80 bg-zinc-950/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        {/* Customer Journey Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto py-2 -mb-px">
          {journeyTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                  isActive
                    ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/50 shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60 border border-transparent'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-400' : 'text-zinc-400'}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Secondary System / Diagnostics Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto py-2 border-t sm:border-t-0 border-zinc-800/60">
          {secondaryTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-zinc-800 text-zinc-100 border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-300 hover:bg-zinc-900 border border-transparent'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
