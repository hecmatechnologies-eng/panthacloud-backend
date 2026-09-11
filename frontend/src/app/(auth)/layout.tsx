import React from 'react';

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-black text-zinc-100 flex flex-col justify-center items-center p-4 relative overflow-hidden">
      {/* Subtle background radial glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-950/20 rounded-full blur-[140px] pointer-events-none" />
      <div className="relative z-10 w-full flex justify-center">
        {children}
      </div>
      <footer className="mt-8 text-center text-xs text-zinc-600 font-mono">
        Fussion Control Plane • Multi-Tenant Containment • Secure Identity
      </footer>
    </div>
  );
}
