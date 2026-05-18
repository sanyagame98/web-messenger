"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { setStoredUser, setToken } from "@/lib/auth";

const USERNAME_RE = /^[a-zA-Z0-9_]{5,32}$/;

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function validate(): string | null {
    if (!email.includes("@")) return "Enter a valid email";
    if (!USERNAME_RE.test(username))
      return "Username must be 5–32 characters: letters, digits and _";
    if (password.length < 6) return "Password must be at least 6 characters";
    return null;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const v = validate();
    if (v) {
      setError(v);
      return;
    }
    setLoading(true);
    try {
      const res = await api.register({
        email: email.trim(),
        username: username.trim(),
        password,
        display_name: displayName.trim() || undefined,
      });
      setToken(res.access_token);
      setStoredUser(res.user);
      router.replace("/chat");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Registration failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 dark:bg-slate-950">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-lg dark:bg-slate-900"
      >
        <h1 className="mb-1 text-2xl font-bold">Create account</h1>
        <p className="mb-6 text-sm text-slate-500">Join Web Messenger.</p>

        <label className="mb-1 block text-sm font-medium">Email</label>
        <input
          type="email"
          className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />

        <label className="mb-1 block text-sm font-medium">
          Username <span className="text-slate-400">(5–32 chars)</span>
        </label>
        <input
          className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />

        <label className="mb-1 block text-sm font-medium">
          Display name <span className="text-slate-400">(optional)</span>
        </label>
        <input
          className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />

        <label className="mb-1 block text-sm font-medium">Password</label>
        <input
          type="password"
          className="mb-4 w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          required
        />

        {error && (
          <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="mb-3 w-full rounded-lg bg-brand-500 px-3 py-2 font-medium text-white transition hover:bg-brand-600 disabled:opacity-60"
        >
          {loading ? "Creating…" : "Create account"}
        </button>

        <p className="text-center text-sm text-slate-500">
          Have an account?{" "}
          <Link href="/login" className="text-brand-500 hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </main>
  );
}
