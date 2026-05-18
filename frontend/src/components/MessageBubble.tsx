import { assetUrl } from "@/lib/api";
import type { ChatMessage, UserPublic } from "@/types";

interface Props {
  message: ChatMessage;
  sender: UserPublic | undefined;
  isMine: boolean;
  showSender: boolean;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function MessageBubble({ message, sender, isMine, showSender }: Props) {
  const img = assetUrl(message.image_url);
  return (
    <div className={`flex ${isMine ? "justify-end" : "justify-start"} px-3`}>
      <div
        className={`max-w-[75%] rounded-2xl px-3 py-2 shadow-sm ${
          isMine
            ? "rounded-br-md bg-brand-500 text-white"
            : "rounded-bl-md bg-white text-slate-900 dark:bg-slate-800 dark:text-slate-100"
        }`}
      >
        {!isMine && showSender && sender && (
          <div className="mb-0.5 text-xs font-semibold text-brand-500">
            {sender.display_name || sender.username}
          </div>
        )}
        {img && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={img}
            alt="attachment"
            className="mb-1 max-h-80 max-w-full rounded-lg object-contain"
          />
        )}
        {message.content && (
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        )}
        <div
          className={`mt-0.5 text-right text-[10px] ${
            isMine ? "text-white/70" : "text-slate-400"
          }`}
        >
          {formatTime(message.created_at)}
        </div>
      </div>
    </div>
  );
}
