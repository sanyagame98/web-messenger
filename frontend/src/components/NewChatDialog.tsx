"use client";

import { useEffect, useRef, useState } from "react";

import { Avatar } from "@/components/Avatar";
import { api, ApiError } from "@/lib/api";
import type { Chat, UserPublic } from "@/types";

interface Props {
  onClose: () => void;
  onCreated: (chat: Chat) => void;
}

type Mode = "direct" | "group";

export function NewChatDialog({ onClose, onCreated }: Props) {
  const [mode, setMode] = useState<Mode>("direct");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserPublic[]>([]);
  const [selected, setSelected] = useState<UserPublic[]>([]);
  const [groupName, setGroupName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.searchUsers(query.trim());
        setResults(res);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed");
      }
    }, 200);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  function toggleSelected(u: UserPublic) {
    setSelected((cur) =>
      cur.find((x) => x.id === u.id) ? cur.filter((x) => x.id !== u.id) : [...cur, u],
    );
  }

  async function handleCreate() {
    setError(null);
    setSubmitting(true);
    try {
      let chat: Chat;
      if (mode === "direct") {
        const user = selected[0] ?? results[0];
        if (!user) {
          setError("Pick a user to chat with");
          return;
        }
        chat = await api.createDirectChat(user.username);
      } else {
        if (!groupName.trim()) {
          setError("Group name is required");
          return;
        }
        chat = await api.createGroupChat(
          groupName.trim(),
          selected.map((u) => u.username),
        );
      }
      onCreated(chat);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Failed to create chat";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">New chat</h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="mb-3 flex gap-2">
          {(["direct", "group"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                setSelected([]);
              }}
              className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-medium ${
                mode === m
                  ? "bg-brand-500 text-white"
                  : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
              }`}
            >
              {m === "direct" ? "Direct" : "Group"}
            </button>
          ))}
        </div>

        {mode === "group" && (
          <input
            placeholder="Group name"
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
            className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
          />
        )}

        {mode === "group" && selected.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {selected.map((u) => (
              <span
                key={u.id}
                className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-1 text-xs text-brand-700 dark:bg-brand-900/40 dark:text-brand-200"
              >
                @{u.username}
                <button
                  className="hover:underline"
                  onClick={() => toggleSelected(u)}
                  aria-label={`Remove ${u.username}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <input
          autoFocus
          placeholder="Search by username…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
        />

        <div className="mb-3 max-h-64 overflow-y-auto scrollbar-thin">
          {results.length === 0 && query.trim() ? (
            <div className="px-2 py-4 text-center text-sm text-slate-500">
              No users found
            </div>
          ) : (
            results.map((u) => {
              const isSelected = !!selected.find((x) => x.id === u.id);
              return (
                <button
                  key={u.id}
                  onClick={() =>
                    mode === "group"
                      ? toggleSelected(u)
                      : setSelected([u])
                  }
                  className={`flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition ${
                    isSelected || (mode === "direct" && selected[0]?.id === u.id)
                      ? "bg-brand-50 dark:bg-brand-900/30"
                      : "hover:bg-slate-100 dark:hover:bg-slate-800"
                  }`}
                >
                  <Avatar name={u.display_name || u.username} url={u.avatar_url} size={36} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">
                      {u.display_name || u.username}
                    </div>
                    <div className="truncate text-xs text-slate-500">@{u.username}</div>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {error && (
          <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
            {error}
          </div>
        )}

        <button
          onClick={handleCreate}
          disabled={submitting}
          className="w-full rounded-lg bg-brand-500 px-3 py-2 font-medium text-white transition hover:bg-brand-600 disabled:opacity-60"
        >
          {submitting ? "Creating…" : mode === "direct" ? "Start chat" : "Create group"}
        </button>
      </div>
    </div>
  );
}
