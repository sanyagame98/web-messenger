type RoofInvokeOptions = Record<string, unknown>;
type RoofInvokeParams = Record<string, unknown>;

type RoofCancellablePromise<T> = Promise<T> & {cancel: () => void};

const TOKEN_KEY = 'roof_access_token';

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

class RoofTransport {
  private updateSocket?: WebSocket;
  private updateListeners = new Set<(update: unknown) => void>();

  public getToken(): string | null {
    try {
      return globalThis.localStorage?.getItem(TOKEN_KEY) || null;
    } catch {
      return null;
    }
  }

  public setToken(token: string | null): void {
    if(!globalThis.localStorage) return;
    if(token) globalThis.localStorage.setItem(TOKEN_KEY, token);
    else globalThis.localStorage.removeItem(TOKEN_KEY);
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

  public login(email: string, password: string) {
    return this.request<{access_token: string; user: unknown}>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({email, password})
    }).then((result) => {
      this.setToken(result.access_token);
      return result;
    });
  }

  public register(email: string, password: string) {
    return this.request<{access_token: string; user: unknown}>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({email, password})
    }).then((result) => {
      this.setToken(result.access_token);
      return result;
    });
  }

  public invoke<T = unknown>(
    method: string,
    params: RoofInvokeParams = {},
    _options: RoofInvokeOptions = {}
  ): RoofCancellablePromise<T> {
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

  public connectUpdates(): void {
    const token = this.getToken();
    if(!token || this.updateSocket) return;
    const url = new URL(getWsBase());
    url.searchParams.set('token', token);
    const socket = new WebSocket(url);
    this.updateSocket = socket;
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.updateListeners.forEach((listener) => listener(data));
      } catch {}
    };
    socket.onclose = () => {
      if(this.updateSocket === socket) this.updateSocket = undefined;
    };
  }

  public logout(): void {
    this.setToken(null);
    this.updateSocket?.close();
    this.updateSocket = undefined;
  }
}

const roofTransport = new RoofTransport();
export default roofTransport;
