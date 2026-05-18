"use client";

import { ChangeEvent, FormEvent, KeyboardEvent, useRef, useState } from "react";

import { api } from "@/lib/api";

interface Props {
  onSend: (content: string, imageUrl?: string) => Promise<void> | void;
  onTyping?: () => void;
  disabled?: boolean;
}

export function Composer({ onSend, onTyping, disabled }: Props) {
  const [text, setText] = useState("");
  const [pendingImage, setPendingImage] = useState<{
    url: string;
    previewUrl: string;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function clearImage() {
    if (pendingImage) URL.revokeObjectURL(pendingImage.previewUrl);
    setPendingImage(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setError("Image is larger than 10 MB");
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const { url } = await api.uploadImage(file);
      setPendingImage({ url, previewUrl: URL.createObjectURL(file) });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const trimmed = text.trim();
    if (!trimmed && !pendingImage) return;
    if (disabled) return;
    setError(null);
    try {
      await onSend(trimmed, pendingImage?.url);
      setText("");
      clearImage();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    }
  }

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    } else if (onTyping) {
      onTyping();
    }
  }

  return (
    <form
      onSubmit={submit}
      className="border-t border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
    >
      {pendingImage && (
        <div className="mb-2 flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={pendingImage.previewUrl}
            alt="preview"
            className="h-16 w-16 rounded-lg object-cover"
          />
          <button
            type="button"
            onClick={clearImage}
            className="text-xs text-red-500 hover:underline"
          >
            Remove
          </button>
        </div>
      )}
      {error && (
        <div className="mb-2 text-xs text-red-500">{error}</div>
      )}
      <div className="flex items-end gap-2">
        <label className="cursor-pointer rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFile}
            disabled={uploading || disabled}
          />
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 17.93 8.83l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKey}
          placeholder={disabled ? "Select a chat to start messaging" : "Write a message…"}
          rows={1}
          disabled={disabled}
          className="max-h-32 flex-1 resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800"
        />
        <button
          type="submit"
          disabled={disabled || uploading || (!text.trim() && !pendingImage)}
          className="rounded-full bg-brand-500 p-2 text-white transition hover:bg-brand-600 disabled:opacity-50"
          aria-label="Send"
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </form>
  );
}
