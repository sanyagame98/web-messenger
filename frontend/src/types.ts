export interface UserPublic {
  id: number;
  username: string;
  display_name: string;
  bio: string;
  avatar_url: string | null;
  last_seen_at: string;
}

export interface UserMe extends UserPublic {
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserMe;
}

export interface ChatMessage {
  id: number;
  chat_id: number;
  sender_id: number | null;
  type: "text" | "image";
  content: string;
  image_url: string | null;
  edited: boolean;
  created_at: string;
}

export interface Chat {
  id: number;
  type: "direct" | "group";
  name: string;
  avatar_url: string | null;
  created_at: string;
  members: UserPublic[];
  last_message: ChatMessage | null;
  unread_count: number;
}
