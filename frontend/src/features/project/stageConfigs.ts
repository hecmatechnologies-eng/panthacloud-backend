import { StageId, ProjectStageConfig } from './types';

export const STAGE_CONFIGS: Record<StageId, ProjectStageConfig> = {
  overview: {
    id: 'overview',
    section: 'BUILD',
    title: 'Overview',
  },
  website: {
    id: 'website',
    section: 'BUILD',
    title: 'Website Connection',
    stepNumber: 1,
  },
  knowledge: {
    id: 'knowledge',
    section: 'BUILD',
    title: 'Knowledge Base',
    stepNumber: 2,
    prerequisite: 'website',
    prerequisiteName: 'Website',
    dependencyTitle: 'Your knowledge base comes next',
    dependencyExplanation:
      'Your assistant needs a website connection before we can organize and verify the content it will use.',
    dependencyStatusLabel: 'Website · Not connected',
    whatToDoFirst:
      'Connect your website so Fussion can discover the content available to your assistant.',
    targetStage: 'website',
    actionLabel: 'Go to Website →',
  },
  assistant: {
    id: 'assistant',
    section: 'BUILD',
    title: 'Assistant Configuration',
    stepNumber: 3,
    prerequisite: 'knowledge',
    prerequisiteName: 'Knowledge',
    dependencyTitle: 'Your assistant comes next',
    dependencyExplanation:
      "Before configuring your assistant's personality and behaviour, give it knowledge it can rely on.",
    dependencyStatusLabel: 'Knowledge base not configured',
    whatToDoFirst: 'Add and verify the content your assistant should use.',
    targetStage: 'knowledge',
    actionLabel: 'Go to Knowledge →',
  },
  integration: {
    id: 'integration',
    section: 'CONNECT',
    title: 'Sandbox Integration',
    stepNumber: 4,
    prerequisite: 'assistant',
    prerequisiteName: 'Assistant',
    dependencyTitle: "Connect your assistant when it's ready",
    dependencyExplanation:
      "The integration stage prepares the assistant for installation on your website. First configure the assistant's identity, behaviour, and capabilities.",
    dependencyStatusLabel: 'Assistant · Not configured',
    whatToDoFirst:
      "First configure the assistant's identity, behaviour, and capabilities.",
    targetStage: 'assistant',
    actionLabel: 'Go to Assistant →',
  },
  preview: {
    id: 'preview',
    section: 'LIVE',
    title: 'Live Visitor Runtime',
    stepNumber: 5,
    prerequisite: 'integration',
    prerequisiteName: 'Integration',
    dependencyTitle: "You're almost ready to go live",
    dependencyExplanation:
      'Your assistant needs to be connected to your website before it can serve real visitors.',
    dependencyStatusLabel: 'Integration · Not connected',
    whatToDoFirst:
      'Complete the sandbox integration and connect your assistant to your website.',
    targetStage: 'integration',
    actionLabel: 'Go to Integration →',
  },
  activity: {
    id: 'activity',
    section: 'LIVE',
    title: 'Activity and Telemetry',
    prerequisite: 'preview',
    prerequisiteName: 'Live Runtime',
    dependencyTitle: 'Activity tracking begins when live',
    dependencyExplanation:
      'Visitor runtime conversations and telemetry logs will stream here once your assistant is deployed.',
    dependencyStatusLabel: 'Live runtime · Not active',
    whatToDoFirst:
      'Connect and deploy your assistant to start observing visitor sessions.',
    targetStage: 'overview',
    actionLabel: 'Go to Overview →',
  },
  settings: {
    id: 'settings',
    section: 'PROJECT',
    title: 'Settings',
  },
};
