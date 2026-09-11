'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '../context';
import { Layers, ArrowRight, Loader2, AlertCircle } from 'lucide-react';

export const LoginForm: React.FC = () => {
  const router = useRouter();
  const { login, error: authError, clearError } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    clearError();

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setLocalError('Please enter your email address.');
      return;
    }
    if (!password) {
      setLocalError('Please enter your password.');
      return;
    }

    setIsSubmitting(true);
    try {
      await login({ email: trimmedEmail, password });
      router.push('/studio');
    } catch (err: any) {
      const displayMsg =
        err?.message || 'Invalid email or password. Please try again.';
      setLocalError(displayMsg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const activeError = localError || authError;

  return (
    <div className="w-full max-w-md bg-zinc-900 border border-zinc-800/90 rounded-2xl p-8 shadow-2xl space-y-6">
      {/* Brand Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 shadow-lg shadow-indigo-950/60 mb-1">
          <Layers className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Fussion <span className="text-indigo-400 font-mono text-sm font-semibold">Studio</span>
          </h1>
          <p className="text-xs text-zinc-400 font-medium mt-0.5">
            AI Integration Engineer for Customer Websites
          </p>
        </div>
      </div>

      <div className="border-t border-zinc-800/60 pt-4">
        <h2 className="text-base font-semibold text-white">Welcome back</h2>
        <p className="text-xs text-zinc-400 mt-0.5">
          Sign in to your private workspace to manage your website assistant.
        </p>
      </div>

      {/* Error Alert Banner */}
      {activeError && (
        <div className="bg-rose-950/40 border border-rose-800/80 rounded-xl p-3.5 flex items-start gap-2.5 text-xs text-rose-200">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="flex-1">{activeError}</div>
        </div>
      )}

      {/* Login Form */}
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-zinc-300 block">
            Email Address
          </label>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="developer@example.com"
            disabled={isSubmitting}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
          />
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-zinc-300 block">
              Password
            </label>
          </div>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            disabled={isSubmitting}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full mt-2 flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs py-2.5 px-4 rounded-xl shadow-lg shadow-indigo-950/50 transition-all disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Signing in...</span>
            </>
          ) : (
            <>
              <span>Sign In</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>
      </form>

      {/* Switch to Signup */}
      <div className="text-center pt-2 border-t border-zinc-800/60 text-xs text-zinc-400">
        Don&apos;t have an account?{' '}
        <Link
          href="/signup"
          className="text-indigo-400 hover:text-indigo-300 font-semibold underline underline-offset-2 transition-colors"
        >
          Sign up
        </Link>
      </div>
    </div>
  );
};
