'use client';

import React from 'react';
import { AssistantView } from '@/features/assistant';

interface AssistantTabProps {
  orgId?: string;
  projectId?: string;
}

export const AssistantTab: React.FC<AssistantTabProps> = ({
  orgId = 'demo-org',
  projectId = 'demo-proj',
}) => {
  return <AssistantView orgId={orgId} projectId={projectId} />;
};
