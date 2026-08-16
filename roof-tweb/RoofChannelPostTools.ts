import showForwardPopup from '@components/popups/forward';
import roofTransport from '@lib/roof/roofTransport';

type RoofChatLike = {peerId?: any; container?: HTMLElement};
type PostInfo = {
  post_id: number;
  channel_id: number;
  views: number;
  author: {mode: 'channel' | 'admin'; name: string; username?: string | null; user_id?: number | null};
  link: string;
};

type ChatSettings = {
  id: number;
  type: string;
  can_manage: boolean;
  post_author_mode?: 'channel' | 'admin';
};

const installed = new WeakSet<object>();
const seen = new Set<string>();
const infoCache = new Map<string, PostInfo>();

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if(className) node.className = className;
  return node;
}

function icon(name: 'eye' | 'more' | 'copy' | 'forward' | 'channel' | 'admin'): string {
  const paths = {
    eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/>',
    more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    forward: '<path d="M15 8l5 4-5 4v-3H9c-3 0-5 1-6 4 0-6 3-9 9-9h3V8z"/>',
    channel: '<path d="M4 10v4l10 4V6L4 10z"/><path d="M14 9c2 1 3 2 3 3s-1 2-3 3M6 14l1 5h3l-1-4"/>',
    admin: '<circle cx="12" cy="8" r="3"/><path d="M5 20c1-4 3.5-6 7-6s6 2 7 6"/>'
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
}

function channelIdOf(chat: RoofChatLike): number {
  const peerId = chat.peerId;
  if(!peerId?.isAnyChat?.()) return 0;
  return Number(peerId.toChatId?.() || 0);
}

function midOf(bubble: HTMLElement): number {
  return Number(bubble.dataset.mid || bubble.getAttribute('data-mid') || 0);
}

function key(channelId: number, postId: number) {
  return `${channelId}:${postId}`;
}

function formatViews(value: number): string {
  if(value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`;
  if(value >= 1_000) return `${(value / 1_000).toFixed(value >= 10_000 ? 0 : 1)}K`;
  return String(value);
}

function toast(text: string) {
  let node = document.querySelector('.roof-channel-post-toast') as HTMLElement | null;
  if(!node) {
    node = el('div', 'roof-channel-post-toast');
    document.body.append(node);
  }
  node.textContent = text;
  node.classList.add('show');
  window.setTimeout(() => node?.classList.remove('show'), 1600);
}

async function getInfo(channelId: number, postId: number, force = false): Promise<PostInfo | null> {
  const cacheKey = key(channelId, postId);
  if(!force && infoCache.has(cacheKey)) return infoCache.get(cacheKey)!;
  try {
    const info = await roofTransport.invoke<PostInfo>('roof.getChannelPostInfo', {channel_id: channelId, post_id: postId});
    infoCache.set(cacheKey, info);
    return info;
  } catch {
    return null;
  }
}

function closeMenus() {
  document.querySelectorAll('.roof-channel-post-menu').forEach((node) => node.remove());
}

async function openMenu(chat: RoofChatLike, bubble: HTMLElement, info: PostInfo, anchor: HTMLElement) {
  closeMenus();
  const menu = el('div', 'roof-channel-post-menu');
  const copy = el('button');
  copy.type = 'button';
  copy.innerHTML = `${icon('copy')}<span>Копировать ссылку</span>`;
  copy.onclick = async() => {
    await navigator.clipboard?.writeText(info.link);
    closeMenus();
    toast('Ссылка на пост скопирована');
  };
  const forward = el('button');
  forward.type = 'button';
  forward.innerHTML = `${icon('forward')}<span>Переслать</span>`;
  forward.onclick = async() => {
    closeMenus();
    const peerId = chat.peerId;
    if(!peerId) return;
    const map: Record<string, number[]> = {};
    map[String(peerId)] = [midOf(bubble)];
    await showForwardPopup(map as any);
  };
  menu.append(copy, forward);
  anchor.parentElement?.append(menu);
}

function paintMeta(chat: RoofChatLike, bubble: HTMLElement, info: PostInfo) {
  const postId = midOf(bubble);
  if(!postId) return;
  let footer = bubble.querySelector<HTMLElement>('.roof-channel-post-meta');
  if(!footer) {
    footer = el('div', 'roof-channel-post-meta');
    const content = bubble.querySelector<HTMLElement>('.bubble-content') || bubble;
    content.append(footer);
  }
  footer.replaceChildren();

  const author = el('span', `roof-channel-post-author ${info.author.mode}`);
  author.innerHTML = `${icon(info.author.mode === 'admin' ? 'admin' : 'channel')}<span>${info.author.mode === 'admin' ? info.author.name : 'От имени канала'}</span>`;

  const views = el('span', 'roof-channel-post-views');
  views.innerHTML = `${icon('eye')}<span>${formatViews(info.views)}</span>`;
  views.dataset.views = String(info.views);

  const moreWrap = el('span', 'roof-channel-post-more-wrap');
  const more = el('button', 'roof-channel-post-more');
  more.type = 'button';
  more.title = 'Действия с публикацией';
  more.innerHTML = icon('more');
  more.onclick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    void openMenu(chat, bubble, info, more);
  };
  moreWrap.append(more);
  footer.append(author, views, moreWrap);
}

async function markViewed(channelId: number, postId: number, bubble: HTMLElement, chat: RoofChatLike) {
  const cacheKey = key(channelId, postId);
  if(seen.has(cacheKey)) return;
  seen.add(cacheKey);
  try {
    const result = await roofTransport.invoke<any>('roof.markChannelPostViewed', {channel_id: channelId, post_ids: [postId]});
    const info = await getInfo(channelId, postId, true);
    if(info) {
      const serverCount = Number(result?.counts?.[String(postId)] ?? info.views);
      info.views = serverCount;
      infoCache.set(cacheKey, info);
      paintMeta(chat, bubble, info);
    }
  } catch {
    seen.delete(cacheKey);
  }
}

async function decorateBubbles(chat: RoofChatLike, observer: IntersectionObserver) {
  const channelId = channelIdOf(chat);
  const container = chat.container;
  if(!channelId || !container) return;
  let settings: ChatSettings;
  try {
    settings = await roofTransport.invoke<ChatSettings>('roof.getChatSettings', {chat_id: channelId});
  } catch {
    return;
  }
  if(settings.type !== 'channel') return;

  const bubbles = Array.from(container.querySelectorAll<HTMLElement>('.bubble[data-mid]'));
  for(const bubble of bubbles) {
    const postId = midOf(bubble);
    if(!postId) continue;
    if(!bubble.dataset.roofPostTools) {
      bubble.dataset.roofPostTools = '1';
      observer.observe(bubble);
    }
    const info = await getInfo(channelId, postId);
    if(info) paintMeta(chat, bubble, info);
  }
  await installPostingModeChip(chat, settings);
}

async function installPostingModeChip(chat: RoofChatLike, settings: ChatSettings) {
  const container = chat.container;
  if(!container || settings.type !== 'channel') return;
  const utils = container.querySelector<HTMLElement>('.topbar .chat-utils');
  if(!utils) return;
  let chip = utils.querySelector<HTMLButtonElement>('.roof-channel-author-mode');
  if(!settings.can_manage) {
    chip?.remove();
    return;
  }
  if(!chip) {
    chip = el('button', 'roof-channel-author-mode');
    chip.type = 'button';
    utils.prepend(chip);
  }
  const mode = settings.post_author_mode === 'admin' ? 'admin' : 'channel';
  chip.dataset.mode = mode;
  chip.innerHTML = `${icon(mode)}<span>${mode === 'admin' ? 'От себя' : 'От канала'}</span>`;
  chip.title = mode === 'admin' ? 'Публикации подписываются вашим именем' : 'Администратор скрыт';
  chip.onclick = async(event) => {
    event.preventDefault();
    event.stopPropagation();
    const next = chip!.dataset.mode === 'admin' ? 'channel' : 'admin';
    await roofTransport.invoke('roof.setChannelPostingMode', {channel_id: settings.id, author_mode: next});
    const fresh = await roofTransport.invoke<ChatSettings>('roof.getChatSettings', {chat_id: settings.id});
    await installPostingModeChip(chat, fresh);
    toast(next === 'admin' ? 'Новые посты будут от вашего имени' : 'Новые посты будут от имени канала');
  };
}

export function installRoofChannelPostTools(chat: RoofChatLike): void {
  if(!chat || installed.has(chat as object)) return;
  const container = chat.container;
  if(!container) return;
  installed.add(chat as object);

  let timer = 0;
  const intersection = new IntersectionObserver((entries) => {
    const channelId = channelIdOf(chat);
    if(!channelId) return;
    entries.forEach((entry) => {
      if(!entry.isIntersecting || entry.intersectionRatio < .55) return;
      const bubble = entry.target as HTMLElement;
      const postId = midOf(bubble);
      if(postId) void markViewed(channelId, postId, bubble, chat);
    });
  }, {threshold: [.55]});

  const schedule = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void decorateBubbles(chat, intersection), 80);
  };
  const mutations = new MutationObserver(schedule);
  mutations.observe(container, {childList: true, subtree: true});
  schedule();

  document.addEventListener('click', (event) => {
    if(!(event.target as HTMLElement)?.closest?.('.roof-channel-post-more-wrap')) closeMenus();
  });

  roofTransport.onUpdate((update: any) => {
    const channelId = channelIdOf(chat);
    if(!channelId || Number(update?.channel_id) !== channelId) return;
    if(update?._ === 'roofUpdateChannelPostViews') {
      const postId = Number(update.post_id || 0);
      const bubble = container.querySelector<HTMLElement>(`.bubble[data-mid="${postId}"]`);
      if(!bubble) return;
      void getInfo(channelId, postId, true).then((info) => info && paintMeta(chat, bubble, info));
    }
    if(update?._ === 'roofUpdateChannelPostingMode') {
      void roofTransport.invoke<ChatSettings>('roof.getChatSettings', {chat_id: channelId})
        .then((settings) => installPostingModeChip(chat, settings));
    }
  });
}
