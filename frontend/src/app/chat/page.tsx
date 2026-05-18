"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Avatar } from "@/components/Avatar";
import { ChatListItem } from "@/components/ChatListItem";
import { Composer } from "@/components/Composer";
import { MessageBubble } from "@/components/MessageBubble";
import { NewChatDialog } from "@/components/NewChatDialog";
import { ProfileDialog } from "@/components/ProfileDialog";
import { api, ApiError } from "@/lib/api";
import { clearAuth, getStoredUser, getToken, setStoredUser } from "@/lib/auth";
import { WsClient, type WsEvent } from "@/lib/ws";
import type { Chat, ChatMessage, UserMe } from "@/types";

export default function ChatPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserMe | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Record<number, ChatMessage[]>>({});
  const [onlineUserIds, setOnlineUserIds] = useState<Set<number>>(new Set());
  const [typingByChat, setTypingByChat] = useState<Record<number, Set<number>>>(
    {},
  );
  const [showNewChat, setShowNewChat] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const wsRef = useRef<WsClient | null>(null);
  const typingTimeoutsRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const selfTypingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auth check + bootstrap
  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    const stored = getStoredUser();
    if (stored) setUser(stored);
    api
      .me()
      .then((u) => {
        setUser(u);
        setStoredUser(u);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAuth();
          router.replace("/login");
        } else {
          setAuthError(err instanceof Error ? err.message : "Failed to load profile");
        }
      });
  }, [router]);

  // Load chats
  const refreshChats = useCallback(async () => {
    try {
      const list = await api.listChats();
      setChats(list);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearAuth();
        router.replace("/login");
      }
    }
  }, [router]);

  useEffect(() => {
    if (user) refreshChats();
  }, [user, refreshChats]);

  // WebSocket
  useEffect(() => {
    if (!user) return;
    const token = getToken();
    if (!token) return;
    const ws = new WsClient(token);
    wsRef.current = ws;
    const off = ws.on((event: WsEvent) => {
      if (event.type === "presence_snapshot") {
        setOnlineUserIds(new Set(event.online_user_ids));
      } else if (event.type === "presence") {
        setOnlineUserIds((cur) => {
          const next = new Set(cur);
          if (event.online) next.add(event.user_id);
          else next.delete(event.user_id);
          return next;
        });
      } else if (event.type === "message") {
        const m = event.message;
        setMessages((cur) => {
          const list = cur[event.chat_id] ?? [];
          if (list.some((x) => x.id === m.id)) return cur;
          return { ...cur, [event.chat_id]: [...list, m] };
        });
        setChats((cur) => {
          const target = cur.find((c) => c.id === event.chat_id);
          if (!target) {
            refreshChats();
            return cur;
          }
          const updated = cur.map((c) =>
            c.id === event.chat_id
              ? {
                  ...c,
                  last_message: m,
                  unread_count:
                    selectedId === event.chat_id || m.sender_id === user.id
                      ? c.unread_count
                      : c.unread_count + 1,
                }
              : c,
          );
          updated.sort((a, b) => {
            const at = a.last_message?.created_at ?? a.created_at;
            const bt = b.last_message?.created_at ?? b.created_at;
            return bt.localeCompare(at);
          });
          return updated;
        });
      } else if (event.type === "typing") {
        if (event.user_id === user.id) return;
        const key = `${event.chat_id}:${event.user_id}`;
        setTypingByChat((cur) => {
          const set = new Set(cur[event.chat_id] ?? []);
          set.add(event.user_id);
          return { ...cur, [event.chat_id]: set };
        });
        if (typingTimeoutsRef.current[key]) {
          clearTimeout(typingTimeoutsRef.current[key]);
        }
        typingTimeoutsRef.current[key] = setTimeout(() => {
          setTypingByChat((cur) => {
            const set = new Set(cur[event.chat_id] ?? []);
            set.delete(event.user_id);
            return { ...cur, [event.chat_id]: set };
          });
        }, 3000);
      }
    });
    ws.start();
    return () => {
      off();
      ws.stop();
      wsRef.current = null;
    };
  }, [user, selectedId, refreshChats]);

  // Load messages when chat is selected
  useEffect(() => {
    if (selectedId == null) return;
    if (messages[selectedId]) return;
    api
      .listMessages(selectedId)
      .then((list) => setMessages((cur) => ({ ...cur, [selectedId]: list })))
      .catch(() => {
        // ignore
      });
  }, [selectedId, messages]);

  // Mark as read when chat is selected/new messages arrive
  const chatMessages = useMemo(
    () => (selectedId != null ? messages[selectedId] ?? [] : []),
    [messages, selectedId],
  );
  const selectedChat = useMemo(
    () => chats.find((c) => c.id === selectedId) ?? null,
    [chats, selectedId],
  );
  useEffect(() => {
    if (!selectedChat || !user) return;
    const last = chatMessages[chatMessages.length - 1];
    if (!last) return;
    if (selectedChat.unread_count === 0 && last.sender_id === user.id) return;
    if (last.sender_id === user.id) return;
    api.markRead(selectedChat.id, last.id).catch(() => undefined);
    setChats((cur) =>
      cur.map((c) => (c.id === selectedChat.id ? { ...c, unread_count: 0 } : c)),
    );
  }, [selectedChat, chatMessages, user]);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages.length, selectedId]);

  async function handleSend(content: string, imageUrl?: string) {
    if (selectedId == null) return;
    const msg = await api.postMessage(selectedId, {
      content,
      image_url: imageUrl ?? null,
    });
    setMessages((cur) => {
      const list = cur[selectedId] ?? [];
      if (list.some((x) => x.id === msg.id)) return cur;
      return { ...cur, [selectedId]: [...list, msg] };
    });
  }

  function emitTyping() {
    if (selectedId == null) return;
    if (selfTypingTimeoutRef.current) return; // throttle
    wsRef.current?.send({ type: "typing", chat_id: selectedId });
    selfTypingTimeoutRef.current = setTimeout(() => {
      selfTypingTimeoutRef.current = null;
    }, 1500);
  }

  function handleLogout() {
    clearAuth();
    wsRef.current?.stop();
    router.replace("/login");
  }

  const typingUsersInSelected: string[] = (() => {
    if (selectedId == null || !selectedChat) return [];
    const ids = typingByChat[selectedId];
    if (!ids || ids.size === 0) return [];
    return Array.from(ids)
      .map((uid) => selectedChat.members.find((m) => m.id === uid))
      .filter((u): u is NonNullable<typeof u> => !!u)
      .map((u) => u.display_name || u.username);
  })();

  const directPeer =
    selectedChat?.type === "direct"
      ? selectedChat.members.find((m) => m.id !== user?.id) ?? null
      : null;
  const directOnline = directPeer ? onlineUserIds.has(directPeer.id) : false;

  if (authError) {
    return (
      <main className="flex h-screen items-center justify-center px-4 text-center text-red-500">
        {authError}
      </main>
    );
  }

  if (!user) {
    return (
      <main className="flex h-screen items-center justify-center text-slate-500">
        Loading…
      </main>
    );
  }

  return (
    <main className="flex h-screen bg-slate-100 dark:bg-slate-950">
      {/* Sidebar */}
      <aside className="flex w-full max-w-sm flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 md:w-80">
        <header className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-3 dark:border-slate-800">
          <button
            className="flex items-center gap-2 text-left"
            onClick={() => setShowProfile(true)}
          >
            <Avatar name={user.display_name || user.username} url={user.avatar_url} size={36} />
            <div className="min-w-0">
              <div className="truncate font-medium leading-tight">
                {user.display_name || user.username}
              </div>
              <div className="truncate text-xs text-slate-500">@{user.username}</div>
            </div>
          </button>
          <div className="flex gap-1">
            <button
              onClick={() => setShowNewChat(true)}
              className="rounded-full bg-brand-500 p-2 text-white hover:bg-brand-600"
              title="New chat"
              aria-label="New chat"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
            <button
              onClick={handleLogout}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              title="Log out"
              aria-label="Log out"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {chats.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-slate-500">
              No chats yet. Tap{" "}
              <span className="inline-flex items-center justify-center rounded-full bg-brand-500 px-2 text-white">
                +
              </span>{" "}
              to start one.
            </div>
          ) : (
            chats.map((c) => {
              const peer =
                c.type === "direct"
                  ? c.members.find((m) => m.id !== user.id)
                  : null;
              const online = peer ? onlineUserIds.has(peer.id) : false;
              return (
                <ChatListItem
                  key={c.id}
                  chat={c}
                  selected={c.id === selectedId}
                  online={online}
                  onClick={() => setSelectedId(c.id)}
                />
              );
            })
          )}
        </div>
      </aside>

      {/* Main */}
      <section className="flex flex-1 flex-col">
        {!selectedChat ? (
          <div className="flex flex-1 items-center justify-center text-slate-400">
            Select a chat to start messaging
          </div>
        ) : (
          <>
            <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
              <Avatar
                name={selectedChat.name}
                url={selectedChat.avatar_url}
                size={40}
                online={selectedChat.type === "direct" ? directOnline : undefined}
              />
              <div className="min-w-0">
                <div className="truncate font-semibold">{selectedChat.name}</div>
                <div className="truncate text-xs text-slate-500">
                  {typingUsersInSelected.length > 0
                    ? `${typingUsersInSelected.join(", ")} typing…`
                    : selectedChat.type === "direct"
                      ? directOnline
                        ? "online"
                        : directPeer
                          ? `last seen ${new Date(directPeer.last_seen_at).toLocaleString()}`
                          : ""
                      : `${selectedChat.members.length} members`}
                </div>
              </div>
            </header>

            <div className="flex-1 space-y-1 overflow-y-auto py-3 scrollbar-thin">
              {chatMessages.map((m, i) => {
                const prev = chatMessages[i - 1];
                const showSender =
                  selectedChat.type === "group" &&
                  m.sender_id !== user.id &&
                  (!prev || prev.sender_id !== m.sender_id);
                const sender = selectedChat.members.find((u) => u.id === m.sender_id);
                return (
                  <MessageBubble
                    key={m.id}
                    message={m}
                    sender={sender}
                    isMine={m.sender_id === user.id}
                    showSender={showSender}
                  />
                );
              })}
              <div ref={messagesEndRef} />
            </div>

            <Composer onSend={handleSend} onTyping={emitTyping} />
          </>
        )}
      </section>

      {showNewChat && (
        <NewChatDialog
          onClose={() => setShowNewChat(false)}
          onCreated={(chat) => {
            setChats((cur) =>
              cur.find((c) => c.id === chat.id) ? cur : [chat, ...cur],
            );
            setSelectedId(chat.id);
            setShowNewChat(false);
          }}
        />
      )}

      {showProfile && (
        <ProfileDialog
          user={user}
          onClose={() => setShowProfile(false)}
          onUpdated={(u) => setUser(u)}
        />
      )}
    </main>
  );
}
