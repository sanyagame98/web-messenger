"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { setStoredUser, setToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.login({ email: email.trim(), password });
      setToken(res.access_token);
      setStoredUser(res.user);
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Не удалось войти");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 text-slate-100">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-3xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
        <div className="mb-7 text-center">
          <div className="mb-2 text-3xl font-black tracking-tight">ROOF</div>
          <p className="text-sm text-slate-400">Вход в аккаунт</p>
        </div>

        <label className="mb-1 block text-sm font-medium">Почта</label>
        <input type="email" className="mb-4 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 outline-none focus:border-brand-500" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />

        <label className="mb-1 block text-sm font-medium">Пароль</label>
        <input type="password" className="mb-4 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 outline-none focus:border-brand-500" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />

        <p className="mb-4 text-xs text-slate-500">Вход напрямую по почте и паролю. Никаких сообщений с кодами.</p>

        {error && <div className="mb-4 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>}

        <button type="submit" disabled={loading} className="mb-4 w-full rounded-xl bg-brand-500 px-3 py-3 font-semibold text-white transition hover:bg-brand-600 disabled:opacity-60">
          {loading ? "Входим…" : "Войти"}
        </button>

        <p className="text-center text-sm text-slate-400">Нет аккаунта? <Link href="/register" className="text-brand-400 hover:underline">Регистрация</Link></p>
      </form>
    </main>
  );
}
