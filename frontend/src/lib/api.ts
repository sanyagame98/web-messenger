import { getToken } from "@/lib/auth";
import type {
  Chat,
  ChatMessage,
  TokenResponse,
  UserMe,
  UserPublic,
} from "@/types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";

export function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function assetUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return apiUrl(path);
}

export function wsUrl(token: string): string {
  const u = new URL(apiUrl("/ws"));
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.searchParams.set("token", token);
  return u.toString();
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { auth = true }: { auth?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(apiUrl(path), { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (data?.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  register(payload: {
    email: string;
    username: string;
    password: string;
    display_name?: string;
  }) {
    return request<TokenResponse>(
      "/api/auth/register",
      { method: "POST", body: JSON.stringify(payload) },
      { auth: false },
    );
  },
  login(payload: { login: string; password: string }) {
    return request<TokenResponse>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify(payload) },
      { auth: false },
    );
  },
  me() {
    return request<UserMe>("/api/auth/me");
  },
  updateMe(payload: { display_name?: string; bio?: string }) {
    return request<UserMe>("/api/auth/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  searchUsers(q: string) {
    return request<UserPublic[]>(`/api/users/search?q=${encodeURIComponent(q)}`);
  },
  listChats() {
    return request<Chat[]>("/api/chats");
  },
  getChat(id: number) {
    return request<Chat>(`/api/chats/${id}`);
  },
  createDirectChat(username: string) {
    return request<Chat>("/api/chats/direct", {
      method: "POST",
      body: JSON.stringify({ username }),
    });
  },
  createGroupChat(name: string, member_usernames: string[]) {
    return request<Chat>("/api/chats/group", {
      method: "POST",
      body: JSON.stringify({ name, member_usernames }),
    });
  },
  listMessages(chatId: number, beforeId?: number) {
    const qs = beforeId ? `?before_id=${beforeId}` : "";
    return request<ChatMessage[]>(`/api/chats/${chatId}/messages${qs}`);
  },
  postMessage(chatId: number, payload: { content?: string; image_url?: string | null }) {
    return request<ChatMessage>(`/api/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  markRead(chatId: number, messageId: number) {
    return request<void>(`/api/chats/${chatId}/messages/read`, {
      method: "POST",
      body: JSON.stringify({ message_id: messageId }),
    });
  },
  uploadImage(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ url: string }>("/api/files/image", {
      method: "POST",
      body: fd,
    });
  },
};
