type RoofInvokeOptions = Record<string, unknown>;
type RoofInvokeParams = Record<string, unknown>;

type RoofCancellablePromise<T> = Promise<T> & {cancel: () => void};

const TOKEN_KEY = 'roof_access_token';
const USER_ID_KEY = 'roof_user_id';

function getApiBase(): string {
  const configured = (globalThis as typeof globalThis & {ROOF_API_BASE?: string}).ROOF_API_BASE;
  return (configured || '/api').replace(/\/+$/, '');
}

function getWsBase(): string {
  const url = new URL(getApiBase(), globalThis.location?.origin || 'http://localhost:8080');
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = '/ws';
  url.search = '';
  return url.toString();
}

function cancellableResolved<T>(value: T): RoofCancellablePromise<T> {
  const promise = Promise.resolve(value) as RoofCancellablePromise<T>;
  promise.cancel = () => {};
  return promise;
}

class RoofTransport {
  private updateSocket?: WebSocket;
  private reconnectTimer?: number;
  private updateListeners = new Set<(update: unknown) => void>();

  public getToken(): string | null {
    try {
      return globalThis.localStorage?.getItem(TOKEN_KEY) || null;
    } catch {
      return null;
    }
  }

  private getUserId(): number {
    try {
      return Number(globalThis.localStorage?.getItem(USER_ID_KEY) || 0);
    } catch {
      return 0;
    }
  }

  public setToken(token: string | null, userId?: number): void {
    if(!globalThis.localStorage) return;
    if(token) {
      globalThis.localStorage.setItem(TOKEN_KEY, token);
      if(userId) globalThis.localStorage.setItem(USER_ID_KEY, String(userId));
    } else {
      globalThis.localStorage.removeItem(TOKEN_KEY);
      globalThis.localStorage.removeItem(USER_ID_KEY);
    }
  }

  private async request<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
    const headers = new Headers(init.headers);
    if(!headers.has('Content-Type') && init.body) headers.set('Content-Type', 'application/json');
    const token = this.getToken();
    if(token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(`${getApiBase()}${path}`, {...init, headers, signal});
    if(!response.ok) {
      let detail = response.statusText;
      try {
        const data = await response.json();
        detail = typeof data?.detail === 'string' ? data.detail : JSON.stringify(data?.detail || data);
      } catch {}
      const error = new Error(detail) as Error & {code?: number; type?: string};
      error.code = response.status;
      error.type = detail.startsWith('ROOF_') ? detail : `ROOF_HTTP_${response.status}`;
      throw error;
    }
    return response.json() as Promise<T>;
  }

  private rememberAuth(result: {access_token: string; user: unknown}) {
    const user = result.user as {id?: number} | undefined;
    this.setToken(result.access_token, user?.id);
    return result;
  }

  public login(email: string, password: string) {
    return this.request<{access_token: string; user: unknown}>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({email, password})
    }).then((result) => this.rememberAuth(result));
  }

  public register(email: string, password: string) {
    return this.request<{access_token: string; user: unknown}>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({email, password})
    }).then((result) => this.rememberAuth(result));
  }

  private localBootstrap(method: string): unknown | undefined {
    const now = Math.floor(Date.now() / 1000);

    if(method === 'help.getConfig') {
      return {
        _: 'config',
        date: now,
        expires: now + 86400,
        test_mode: false,
        this_dc: 1,
        dc_options: [],
        dc_txt_domain_name: 'roof.local',
        chat_size_max: 200,
        megagroup_size_max: 200000,
        forwarded_count_max: 100,
        online_update_period_ms: 120000,
        offline_blur_timeout_ms: 5000,
        offline_idle_timeout_ms: 30000,
        online_cloud_timeout_ms: 300000,
        notify_cloud_delay_ms: 30000,
        notify_default_delay_ms: 1500,
        push_chat_period_ms: 60000,
        push_chat_limit: 2,
        saved_gifs_limit: 200,
        edit_time_limit: 172800,
        revoke_time_limit: 172800,
        revoke_pm_time_limit: 172800,
        rating_e_decay: 2419200,
        stickers_recent_limit: 200,
        channels_read_media_period: 604800,
        tmp_sessions: 0,
        call_receive_timeout_ms: 20000,
        call_ring_timeout_ms: 90000,
        call_connect_timeout_ms: 30000,
        call_packet_timeout_ms: 10000,
        me_url_prefix: 'roof://',
        autoupdate_url_prefix: '',
        gif_search_username: '',
        venue_search_username: '',
        img_search_username: '',
        static_maps_provider: '',
        caption_length_max: 4096,
        message_length_max: 4096,
        webfile_dc_id: 1,
        suggested_lang_code: 'en',
        lang_pack_version: 0,
        base_lang_pack_version: 0,
        pFlags: {}
      };
    }

    if(method === 'help.getAppConfig') {
      return {
        _: 'help.appConfig',
        hash: 1,
        config: {
          dialogs_pinned_limit_default: 5,
          dialogs_pinned_limit_premium: 10,
          dialogs_folder_pinned_limit_default: 5,
          dialogs_folder_pinned_limit_premium: 10,
          dialog_filters_limit_default: 10,
          dialog_filters_limit_premium: 20,
          stickers_faved_limit_default: 5,
          stickers_faved_limit_premium: 10,
          reactions_user_max_default: 1,
          reactions_user_max_premium: 3,
          about_length_limit_default: 280,
          about_length_limit_premium: 280,
          topics_pinned_limit: 5,
          caption_length_limit_default: 4096,
          caption_length_limit_premium: 4096,
          chatlist_invites_limit_default: 3,
          chatlist_invites_limit_premium: 10,
          chatlists_joined_limit_default: 2,
          chatlists_joined_limit_premium: 20,
          channels_limit_default: 500,
          channels_limit_premium: 1000,
          channels_public_limit_default: 10,
          channels_public_limit_premium: 20,
          saved_gifs_limit_default: 200,
          saved_gifs_limit_premium: 400,
          dialog_filters_chats_limit_default: 100,
          dialog_filters_chats_limit_premium: 200,
          upload_max_fileparts_default: 4000,
          upload_max_fileparts_premium: 8000,
          recommended_channels_limit_default: 10,
          recommended_channels_limit_premium: 20,
          saved_dialogs_pinned_limit_default: 5,
          saved_dialogs_pinned_limit_premium: 10,
          ignore_restriction_reasons: []
        }
      };
    }

    if(method === 'help.getTimezonesList') {
      return {_: 'help.timezonesList', timezones: [], hash: 1};
    }

    if(method === 'help.getPeerColors' || method === 'help.getPeerProfileColors') {
      return {_: 'help.peerColors', colors: [], hash: 1};
    }

    if(method === 'contacts.getStatuses') return [];
    if(method === 'messages.getTopPeers') {
      return {_: 'contacts.topPeers', categories: [], chats: [], users: []};
    }
    if(method === 'messages.getSavedDialogs') {
      return {_: 'messages.savedDialogs', dialogs: [], messages: [], chats: [], users: []};
    }
    if(method === 'account.getGlobalPrivacySettings') {
      return {_: 'globalPrivacySettings', pFlags: {}};
    }
    if(method === 'account.getContentSettings') {
      return {_: 'account.contentSettings', pFlags: {}};
    }

    return undefined;
  }

  public invoke<T = unknown>(
    method: string,
    params: RoofInvokeParams = {},
    _options: RoofInvokeOptions = {}
  ): RoofCancellablePromise<T> {
    const local = this.localBootstrap(method);
    if(local !== undefined) return cancellableResolved(local as T);

    const controller = new AbortController();
    const promise = this.request<T>(
      '/roof/invoke',
      {method: 'POST', body: JSON.stringify({method, params})},
      controller.signal
    ) as RoofCancellablePromise<T>;
    promise.cancel = () => controller.abort();
    return promise;
  }

  public onUpdate(listener: (update: unknown) => void): () => void {
    this.updateListeners.add(listener);
    return () => this.updateListeners.delete(listener);
  }

  private emit(update: unknown): void {
    this.updateListeners.forEach((listener) => listener(update));
  }

  private normalizeSocketUpdate(data: any): unknown | undefined {
    if(!data) return;
    if(data.roof_update) return data.roof_update;

    if(data.type === 'presence') {
      return {
        _: 'updateUserStatus',
        user_id: Number(data.user_id),
        status: data.online ?
          {_: 'userStatusOnline', expires: Math.floor(Date.now() / 1000) + 60} :
          {_: 'userStatusOffline', was_online: Math.floor(Date.now() / 1000)}
      };
    }

    if(data.type === 'typing') {
      return {
        _: 'updateUserTyping',
        user_id: Number(data.user_id),
        action: {_: 'sendMessageTypingAction'}
      };
    }

    if(data.type === 'roof_message') {
      const message = data.message || {};
      const me = this.getUserId();
      const memberIds = Array.isArray(data.member_user_ids) ? data.member_user_ids.map(Number) : [];
      let peer: any;
      if(data.chat_type === 'direct') {
        const other = memberIds.find((id: number) => id !== me) || Number(message.sender_id || 0);
        peer = {_: 'peerUser', user_id: other};
      } else {
        peer = {_: 'peerChat', chat_id: Number(data.chat_id)};
      }
      const item: any = {
        _: 'message',
        id: Number(message.id),
        peer_id: peer,
        date: Math.floor(new Date(message.created_at || Date.now()).getTime() / 1000),
        message: String(message.content || ''),
        pFlags: Number(message.sender_id) === me ? {out: true} : {}
      };
      if(message.sender_id) item.from_id = {_: 'peerUser', user_id: Number(message.sender_id)};
      return {_: 'updateNewMessage', message: item, pts: Number(message.id), pts_count: 1};
    }

    return;
  }

  public connectUpdates(): void {
    const token = this.getToken();
    if(!token || this.updateSocket) return;
    if(this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }

    const url = new URL(getWsBase());
    url.searchParams.set('token', token);
    const socket = new WebSocket(url);
    this.updateSocket = socket;
    socket.onmessage = (event) => {
      try {
        const update = this.normalizeSocketUpdate(JSON.parse(event.data));
        if(update) this.emit(update);
      } catch {}
    };
    socket.onclose = () => {
      if(this.updateSocket === socket) this.updateSocket = undefined;
      if(this.getToken()) {
        this.reconnectTimer = globalThis.setTimeout(() => {
          this.reconnectTimer = undefined;
          this.connectUpdates();
        }, 1500) as unknown as number;
      }
    };
  }

  public logout(): void {
    this.setToken(null);
    if(this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = undefined;
    this.updateSocket?.close();
    this.updateSocket = undefined;
  }
}

const roofTransport = new RoofTransport();
export default roofTransport;
