'use client';

import React from 'react';

interface StudioCanvasProps {
  children?: React.ReactNode;
  className?: string;
}

export const StudioCanvas: React.FC<StudioCanvasProps> = ({ children, className = '' }) => {
  return (
    <div
      data-testid="studio-canvas"
      className={`relative min-h-screen bg-[var(--canvas)] text-[var(--text-primary)] flex flex-col font-sans selection:bg-[var(--color-purple)] selection:text-white overflow-x-hidden transition-colors duration-150 ${className}`}
    >
      {/* Background Canvas Layer */}
      <div
        data-testid="canvas-background-layer"
        className="fixed inset-0 pointer-events-none select-none z-0 overflow-hidden"
        aria-hidden="true"
      >
        {/* Atmospheric Ambient Gradients */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `
              radial-gradient(circle at 18% 12%, var(--canvas-block) 0%, transparent 45%),
              radial-gradient(circle at 85% 65%, var(--canvas-block) 0%, transparent 50%),
              radial-gradient(ellipse at 50% 100%, var(--canvas-block) 0%, transparent 60%)
            `,
          }}
        />

        {/* Technical Fine Grid Overlay (CSS Gradients) */}
        <div
          data-testid="canvas-grid-layer"
          className="absolute inset-0"
          style={{
            backgroundImage: `
              linear-gradient(to right, var(--canvas-grid) 1px, transparent 1px),
              linear-gradient(to bottom, var(--canvas-grid) 1px, transparent 1px)
            `,
            backgroundSize: '40px 40px',
            opacity: 0.65,
          }}
        />

        {/* Sparse Translucent Geometric Blocks (Aligned to 40px grid) */}
        <div
          className="absolute top-[80px] left-[120px] w-[40px] h-[40px]"
          style={{
            backgroundColor: 'var(--canvas-block)',
            border: '1px solid var(--canvas-block-border)',
          }}
        />
        <div
          className="hidden md:block absolute top-[280px] right-[200px] w-[80px] h-[40px]"
          style={{
            backgroundColor: 'var(--canvas-block)',
            border: '1px solid var(--canvas-block-border)',
          }}
        />
        <div
          className="hidden lg:block absolute bottom-[160px] left-[240px] w-[40px] h-[40px]"
          style={{
            backgroundColor: 'var(--canvas-block)',
            border: '1px solid var(--canvas-block-border)',
          }}
        />
        <div
          className="hidden sm:block absolute top-[480px] left-[80px] w-[40px] h-[80px]"
          style={{
            backgroundColor: 'var(--canvas-block)',
            border: '1px solid var(--canvas-block-border)',
          }}
        />

        {/* Subtle Technical Intersection Crosshairs */}
        <div
          className="absolute top-[160px] left-[280px] font-mono text-[11px] leading-none select-none"
          style={{ color: 'var(--canvas-marker)' }}
        >
          +
        </div>
        <div
          className="hidden sm:block absolute top-[440px] right-[360px] font-mono text-[11px] leading-none select-none"
          style={{ color: 'var(--canvas-marker)' }}
        >
          +
        </div>
        <div
          className="hidden lg:block absolute bottom-[240px] right-[160px] font-mono text-[11px] leading-none select-none"
          style={{ color: 'var(--canvas-marker)' }}
        >
          +
        </div>
        <div
          className="absolute top-[120px] right-[120px] font-mono text-[11px] leading-none select-none"
          style={{ color: 'var(--canvas-marker)' }}
        >
          +
        </div>

        {/* Soft Vignette / Canvas Edge Falloff */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'radial-gradient(ellipse at center, transparent 55%, var(--canvas) 100%)',
            opacity: 0.6,
          }}
        />
      </div>

      {/* Foreground Content Layer */}
      <div className="relative z-10 flex-1 flex flex-col">
        {children}
      </div>
    </div>
  );
};
