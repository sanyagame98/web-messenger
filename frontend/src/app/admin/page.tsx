"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { apiUrl } from "@/lib/api";
import { getToken } from "@/lib/auth";

type AdminUser = {
  id: number;
  email: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  stars: number;
  premium_until: string | null;
  is_premium: boolean;
  is_verified: boolean;
  is_admin: boolean;
  last_seen_at: string;
};

async function adminRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(apiUrl(path), { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export default function RoofAdminBotPage() {
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [query, setQuery] = useState("");
  const [stars, setStars] = useState<Record<number, string>>({});
  const [days, setDays] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const loadUsers = useCallback(async () => {
    try {
      setError(null);
      const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
      const data = await adminRequest<AdminUser[]>(`/api/users/admin/users${suffix}`);
      setUsers(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить пользователей");
    }
  }, [query]);

  useEffect(() => {
    const timer = setTimeout(loadUsers, 200);
    return () => clearTimeout(timer);
  }, [loadUsers]);

  async function updateUser(userId: number, action: () => Promise<AdminUser>) {
    setBusy(userId);
    setError(null);
    try {
      const updated = await action();
      setUsers((current) => current.map((u) => (u.id === userId ? updated : u)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка операции");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3">
          <button onClick={() => router.push("/chat")} className="rounded-xl px-3 py-2 hover:bg-slate-800">
            ←
          </button>
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-sky-500 text-xl">🤖</div>
          <div className="min-w-0 flex-1">
            <div className="font-semibold">Roof Admin Bot</div>
            <div className="text-xs text-slate-400">Все пользователи · Roof Stars · Premium · официальная галочка</div>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl p-4">
        <div className="mb-4 rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <div className="mb-2 text-sm text-slate-400">Поиск пользователя</div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="email, @username или имя"
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none focus:border-sky-500"
          />
        </div>

        {error && <div className="mb-4 rounded-xl border border-red-900 bg-red-950/40 px-4 py-3 text-red-300">{error}</div>}

        <div className="space-y-3">
          {users.map((user) => (
            <section key={user.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
              <div className="flex flex-wrap items-start gap-4">
                <div className="flex min-w-64 flex-1 items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-lg font-semibold">
                    {(user.display_name || user.username).slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1 font-semibold">
                      <span>{user.display_name || user.username}</span>
                      {user.is_verified && <span title="Официальный аккаунт" className="text-sky-400">✓</span>}
                      {user.is_premium && <span title="Roof Premium" className="text-purple-400">★</span>}
                      {user.is_admin && <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-xs text-sky-300">ADMIN</span>}
                    </div>
                    <div className="truncate text-sm text-slate-400">@{user.username} · {user.email}</div>
                    <div className="mt-1 text-sm">⭐ {user.stars.toLocaleString("ru-RU")} Roof Stars</div>
                    <div className="text-xs text-slate-500">
                      Premium: {user.premium_until ? new Date(user.premium_until).toLocaleString("ru-RU") : "нет"}
                    </div>
                  </div>
                </div>

                <div className="grid min-w-72 flex-[2] gap-2 md:grid-cols-3">
                  <div className="rounded-xl bg-slate-950 p-3">
                    <div className="mb-2 text-xs text-slate-400">Выдать Roof Stars</div>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        min={1}
                        value={stars[user.id] ?? "100"}
                        onChange={(e) => setStars((s) => ({ ...s, [user.id]: e.target.value }))}
                        className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-2 py-2"
                      />
                      <button
                        disabled={busy === user.id}
                        onClick={() => updateUser(user.id, () => adminRequest(`/api/users/admin/users/${user.id}/stars`, {
                          method: "POST",
                          body: JSON.stringify({ amount: Number(stars[user.id] ?? 100) }),
                        }))}
                        className="rounded-lg bg-amber-500 px-3 py-2 font-medium text-black disabled:opacity-50"
                      >
                        +
                      </button>
                    </div>
                  </div>

                  <div className="rounded-xl bg-slate-950 p-3">
                    <div className="mb-2 text-xs text-slate-400">Подарить Premium без списания звёзд</div>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        min={1}
                        value={days[user.id] ?? "30"}
                        onChange={(e) => setDays((s) => ({ ...s, [user.id]: e.target.value }))}
                        className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-2 py-2"
                      />
                      <button
                        disabled={busy === user.id}
                        onClick={() => updateUser(user.id, () => adminRequest(`/api/users/admin/users/${user.id}/premium`, {
                          method: "POST",
                          body: JSON.stringify({ days: Number(days[user.id] ?? 30) }),
                        }))}
                        className="rounded-lg bg-purple-500 px-3 py-2 font-medium text-white disabled:opacity-50"
                      >
                        🎁
                      </button>
                    </div>
                    {user.is_premium && (
                      <button
                        disabled={busy === user.id}
                        onClick={() => updateUser(user.id, () => adminRequest(`/api/users/admin/users/${user.id}/premium`, { method: "DELETE" }))}
                        className="mt-2 text-xs text-slate-400 hover:text-red-300"
                      >
                        снять Premium
                      </button>
                    )}
                  </div>

                  <div className="rounded-xl bg-slate-950 p-3">
                    <div className="mb-2 text-xs text-slate-400">Официальная галочка</div>
                    <button
                      disabled={busy === user.id}
                      onClick={() => updateUser(user.id, () => adminRequest(`/api/users/admin/users/${user.id}/verified`, {
                        method: "POST",
                        body: JSON.stringify({ verified: !user.is_verified }),
                      }))}
                      className={`w-full rounded-lg px-3 py-2 font-medium disabled:opacity-50 ${user.is_verified ? "bg-slate-800 text-slate-200" : "bg-sky-500 text-white"}`}
                    >
                      {user.is_verified ? "Снять ✓" : "Выдать ✓"}
                    </button>
                  </div>
                </div>
              </div>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}
