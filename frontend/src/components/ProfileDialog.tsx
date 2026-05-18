"use client";

import { useState } from "react";

import { Avatar } from "@/components/Avatar";
import { api, ApiError } from "@/lib/api";
import { setStoredUser } from "@/lib/auth";
import type { UserMe } from "@/types";

interface Props {
  user: UserMe;
  onClose: () => void;
  onUpdated: (user: UserMe) => void;
}

export function ProfileDialog({ user, onClose, onUpdated }: Props) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [bio, setBio] = useState(user.bio);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    setSaving(true);
    try {
      const updated = await api.updateMe({ display_name: displayName, bio });
      setStoredUser(updated);
      onUpdated(updated);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Save failed");
    } finally {
      setSaving(false);
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
          <h2 className="text-lg font-semibold">Profile</h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="mb-4 flex items-center gap-3">
          <Avatar name={user.display_name || user.username} url={user.avatar_url} size={56} />
          <div>
            <div className="font-medium">@{user.username}</div>
            <div className="text-sm text-slate-500">{user.email}</div>
          </div>
        </div>

        <label className="mb-1 block text-sm font-medium">Display name</label>
        <input
          className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          maxLength={64}
        />

        <label className="mb-1 block text-sm font-medium">Bio</label>
        <textarea
          className="mb-3 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
          value={bio}
          onChange={(e) => setBio(e.target.value)}
          rows={3}
          maxLength={280}
        />

        {error && (
          <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
            {error}
          </div>
        )}

        <button
          onClick={save}
          disabled={saving}
          className="w-full rounded-lg bg-brand-500 px-3 py-2 font-medium text-white transition hover:bg-brand-600 disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
