'use client';

import React from 'react';
import { KnowledgeBaseView } from '@/features/knowledge';

interface KnowledgeTabProps {
  orgId?: string;
  projectId?: string;
}

export const KnowledgeTab: React.FC<KnowledgeTabProps> = ({ orgId, projectId }) => {
  return <KnowledgeBaseView orgId={orgId} projectId={projectId} />;
};
