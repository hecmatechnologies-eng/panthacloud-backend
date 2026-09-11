'use client';

import React from 'react';
import { IntegrationView } from '@/features/integrations';

interface IntegrationTabProps {
  orgId?: string;
  projectId?: string;
}

export const IntegrationTab: React.FC<IntegrationTabProps> = ({ orgId, projectId }) => {
  return <IntegrationView orgId={orgId} projectId={projectId} />;
};
