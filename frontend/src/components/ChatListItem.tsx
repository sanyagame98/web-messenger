import { Avatar } from "@/components/Avatar";
import type { Chat } from "@/types";

interface Props {
  chat: Chat;
  selected: boolean;
  online: boolean;
  onClick: () => void;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  if (
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate()
  ) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate()
  ) {
    return "Yesterday";
  }
  return d.toLocaleDateString();
}

export function ChatListItem({ chat, selected, online, onClick }: Props) {
  const last = chat.last_message;
  const preview = last
    ? last.type === "image"
      ? "📷 Photo"
      : last.content
    : "No messages yet";
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-3 px-3 py-2 text-left transition ${
        selected
          ? "bg-brand-50 dark:bg-brand-900/30"
          : "hover:bg-slate-100 dark:hover:bg-slate-800"
      }`}
    >
      <Avatar name={chat.name} url={chat.avatar_url} size={44} online={chat.type === "direct" ? online : undefined} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate font-medium">{chat.name || "Untitled"}</span>
          {last && (
            <span className="shrink-0 text-xs text-slate-400">
              {formatTime(last.created_at)}
            </span>
          )}
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-sm text-slate-500 dark:text-slate-400">
            {preview}
          </span>
          {chat.unread_count > 0 && (
            <span className="rounded-full bg-brand-500 px-2 py-0.5 text-xs font-semibold text-white">
              {chat.unread_count}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
