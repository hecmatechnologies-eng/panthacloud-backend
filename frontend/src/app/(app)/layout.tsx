import React from 'react';
import { ProtectedRoute } from '@/features/auth';
import { ProjectProvider } from '@/features/project';
import { AppShell } from '@/components/layout';

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ProtectedRoute>
      <ProjectProvider>
        <AppShell>{children}</AppShell>
      </ProjectProvider>
    </ProtectedRoute>
  );
}
