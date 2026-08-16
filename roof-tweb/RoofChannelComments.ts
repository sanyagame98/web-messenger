import roofTransport from '@lib/roof/roofTransport';

type RoofChatLike = {peerId?: any; container?: HTMLElement};
type Reaction = {emoji: string; count: number; chosen: boolean};
type Comment = {
  id: number;
  message: string;
  created_at: string;
  reply_to?: number | null;
  sender?: {id: number; name: string; username: string; avatar_url?: string | null} | null;
  reactions: Reaction[];
  can_edit: boolean;
};
type DiscussionState = {
  post: {id: number; channel_id: number; channel_title: string; message: string; created_at: string};
  discussion_chat_id: number;
  joined: boolean;
  count: number;
  comments: Comment[];
  available_reactions: string[];
};

const instances = new WeakMap<object, MutationObserver>();
const settingsCache = new Map<number, {type: string; comments_enabled: boolean}>();
let activePanel: {channelId: number; postId: number; overlay: HTMLElement; refresh: () => Promise<void>} | null = null;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if(className) node.className = className;
  return node;
}

function icon(name: 'comments' | 'back' | 'reply' | 'trash' | 'send'): string {
  const paths = {
    comments: '<path d="M21 15a4 4 0 0 1-4 4H8l-5 3v-15a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8M8 13h5"/>',
    back: '<path d="M15 18l-6-6 6-6"/>',
    reply: '<path d="M9 17l-6-5 6-5v3c7 0 10 3 12 8-3-3-6-4-12-4v3z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6"/>',
    send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>'
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
}

function channelIdOf(chat: RoofChatLike): number {
  const peerId = chat.peerId;
  if(!peerId?.isAnyChat?.()) return 0;
  return Number(peerId.toChatId?.() || 0);
}

async function getSettings(channelId: number, force = false): Promise<{type: string; comments_enabled: boolean} | null> {
  if(!force && settingsCache.has(channelId)) return settingsCache.get(channelId)!;
  try {
    const data = await roofTransport.invoke<any>('roof.getChatSettings', {chat_id: channelId});
    const value = {type: String(data.type || ''), comments_enabled: Boolean(data.comments_enabled)};
    settingsCache.set(channelId, value);
    return value;
  } catch {
    return null;
  }
}

function bubbleMid(bubble: HTMLElement): number {
  return Number(bubble.dataset.mid || bubble.getAttribute('data-mid') || 0);
}

async function decorate(chat: RoofChatLike): Promise<void> {
  const channelId = channelIdOf(chat);
  const container = chat.container;
  if(!channelId || !container) return;
  const settings = await getSettings(channelId);
  if(!settings || settings.type !== 'channel' || !settings.comments_enabled) {
    container.querySelectorAll('.roof-post-comments').forEach((node) => node.remove());
    return;
  }

  const bubbles = Array.from(container.querySelectorAll<HTMLElement>('.bubble[data-mid]'));
  const pending = bubbles.filter((bubble) => bubbleMid(bubble) > 0 && !bubble.querySelector('.roof-post-comments'));
  if(!pending.length) return;
  const postIds = pending.map(bubbleMid);
  let counts: Record<string, number> = {};
  try {
    const result = await roofTransport.invoke<any>('roof.getPostCommentCounts', {channel_id: channelId, post_ids: postIds});
    counts = result.counts || {};
  } catch {
    return;
  }

  pending.forEach((bubble) => {
    const postId = bubbleMid(bubble);
    const button = el('button', 'roof-post-comments');
    button.type = 'button';
    const count = Number(counts[String(postId)] || 0);
    button.innerHTML = `${icon('comments')}<span>${count ? `${count} ${commentWord(count)}` : 'Оставить комментарий'}</span><b>›</b>`;
    button.dataset.postId = String(postId);
    button.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      void openDiscussion(channelId, postId);
    };
    const bubbleContent = bubble.querySelector<HTMLElement>('.bubble-content') || bubble;
    bubbleContent.append(button);
  });
}

function commentWord(count: number): string {
  const n10 = count % 10;
  const n100 = count % 100;
  if(n10 === 1 && n100 !== 11) return 'комментарий';
  if(n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'комментария';
  return 'комментариев';
}

function time(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
}

function updateFooterCount(channelId: number, postId: number, count: number) {
  document.querySelectorAll<HTMLElement>(`.roof-post-comments[data-post-id="${postId}"]`).forEach((button) => {
    if(channelId !== channelIdOf((window as any).__roofCurrentChat || {})) {
      // The selector is already scoped by a globally unique message id in current Roof DB.
    }
    const label = button.querySelector('span');
    if(label) label.textContent = count ? `${count} ${commentWord(count)}` : 'Оставить комментарий';
  });
}

async function openDiscussion(channelId: number, postId: number): Promise<void> {
  activePanel?.overlay.remove();
  const overlay = el('div', 'roof-discussion-overlay');
  const panel = el('div', 'roof-discussion-panel');
  overlay.append(panel);
  document.body.append(overlay);

  let state: DiscussionState | null = null;
  let replyTo: Comment | null = null;

  const header = el('header', 'roof-discussion-header');
  const back = el('button', 'roof-discussion-icon');
  back.type = 'button';
  back.innerHTML = icon('back');
  back.onclick = () => { overlay.remove(); if(activePanel?.overlay === overlay) activePanel = null; };
  const heading = el('div', 'roof-discussion-heading');
  const headingTitle = el('strong');
  headingTitle.textContent = 'Комментарии';
  const headingCount = el('span');
  heading.append(headingTitle, headingCount);
  header.append(back, heading);

  const scroll = el('main', 'roof-discussion-scroll');
  const composer = el('footer', 'roof-discussion-composer');
  panel.append(header, scroll, composer);

  const refresh = async() => {
    state = await roofTransport.invoke<DiscussionState>('roof.getPostDiscussion', {channel_id: channelId, post_id: postId});
    render();
  };
  activePanel = {channelId, postId, overlay, refresh};

  const render = () => {
    if(!state) return;
    headingCount.textContent = state.count ? `${state.count} ${commentWord(state.count)}` : 'Нет комментариев';
    updateFooterCount(channelId, postId, state.count);
    scroll.replaceChildren();

    const post = el('section', 'roof-discussion-post');
    const channel = el('strong');
    channel.textContent = state.post.channel_title;
    const text = el('div');
    text.textContent = state.post.message || 'Публикация';
    post.append(channel, text);
    scroll.append(post);

    if(!state.comments.length) {
      const empty = el('div', 'roof-discussion-empty');
      empty.innerHTML = '<strong>Комментариев пока нет</strong><span>Начните обсуждение этой публикации</span>';
      scroll.append(empty);
    }

    const byId = new Map(state.comments.map((item) => [item.id, item]));
    state.comments.forEach((comment) => {
      const row = el('article', 'roof-discussion-comment');
      row.dataset.commentId = String(comment.id);
      const avatar = el('div', 'roof-discussion-avatar');
      if(comment.sender?.avatar_url) {
        const img = el('img'); img.src = comment.sender.avatar_url; avatar.append(img);
      } else avatar.textContent = (comment.sender?.name || '?').slice(0, 1).toUpperCase();
      const body = el('div', 'roof-discussion-comment-body');
      const meta = el('div', 'roof-discussion-comment-meta');
      const name = el('strong'); name.textContent = comment.sender?.name || 'Пользователь';
      const at = el('span'); at.textContent = time(comment.created_at);
      meta.append(name, at);
      if(comment.reply_to) {
        const parent = byId.get(comment.reply_to);
        const reply = el('button', 'roof-discussion-replied');
        reply.type = 'button';
        reply.innerHTML = `<strong>${escapeHtml(parent?.sender?.name || 'Сообщение')}</strong><span>${escapeHtml((parent?.message || '').slice(0, 90))}</span>`;
        reply.onclick = () => scroll.querySelector<HTMLElement>(`[data-comment-id="${comment.reply_to}"]`)?.scrollIntoView({behavior: 'smooth', block: 'center'});
        body.append(meta, reply);
      } else body.append(meta);
      const message = el('div', 'roof-discussion-text'); message.textContent = comment.message; body.append(message);

      const actions = el('div', 'roof-discussion-actions');
      const replyButton = el('button'); replyButton.type = 'button'; replyButton.innerHTML = `${icon('reply')}<span>Ответить</span>`;
      replyButton.onclick = () => { replyTo = comment; renderComposer(); };
      actions.append(replyButton);
      if(comment.can_edit) {
        const remove = el('button', 'danger'); remove.type = 'button'; remove.innerHTML = `${icon('trash')}<span>Удалить</span>`;
        remove.onclick = async() => {
          if(!confirm('Удалить комментарий?')) return;
          await roofTransport.invoke('roof.deletePostComment', {channel_id: channelId, post_id: postId, comment_id: comment.id});
          await refresh();
        };
        actions.append(remove);
      }
      body.append(actions);

      const reactions = el('div', 'roof-discussion-reactions');
      comment.reactions.forEach((reaction) => {
        const chip = el('button', `roof-discussion-reaction${reaction.chosen ? ' chosen' : ''}`);
        chip.type = 'button'; chip.textContent = `${reaction.emoji} ${reaction.count}`;
        chip.onclick = () => void react(comment.id, reaction.emoji);
        reactions.append(chip);
      });
      const plus = el('button', 'roof-discussion-reaction add'); plus.type = 'button'; plus.textContent = '＋';
      plus.onclick = () => openReactionPicker(plus, comment.id);
      reactions.append(plus);
      body.append(reactions);
      row.append(avatar, body);
      scroll.append(row);
    });
    renderComposer();
    requestAnimationFrame(() => { scroll.scrollTop = scroll.scrollHeight; });
  };

  const react = async(commentId: number, emoji: string) => {
    await roofTransport.invoke('roof.reactPostComment', {channel_id: channelId, post_id: postId, comment_id: commentId, emoji});
    await refresh();
  };

  const openReactionPicker = (anchor: HTMLElement, commentId: number) => {
    document.querySelector('.roof-discussion-reaction-picker')?.remove();
    const picker = el('div', 'roof-discussion-reaction-picker');
    (state?.available_reactions || []).slice(0, 20).forEach((emoji) => {
      const button = el('button'); button.type = 'button'; button.textContent = emoji;
      button.onclick = async() => { picker.remove(); await react(commentId, emoji); };
      picker.append(button);
    });
    anchor.parentElement?.append(picker);
  };

  const renderComposer = () => {
    if(!state) return;
    composer.replaceChildren();
    if(!state.joined) {
      const join = el('button', 'roof-discussion-join');
      join.type = 'button'; join.textContent = 'Присоединиться к обсуждению';
      join.onclick = async() => {
        state = await roofTransport.invoke<DiscussionState>('roof.joinPostDiscussion', {channel_id: channelId, post_id: postId});
        render();
      };
      composer.append(join);
      return;
    }
    const wrap = el('div', 'roof-discussion-input-wrap');
    if(replyTo) {
      const reply = el('div', 'roof-discussion-compose-reply');
      reply.innerHTML = `<div><strong>${escapeHtml(replyTo.sender?.name || 'Пользователь')}</strong><span>${escapeHtml(replyTo.message.slice(0, 100))}</span></div><button type="button">×</button>`;
      (reply.querySelector('button') as HTMLButtonElement).onclick = () => { replyTo = null; renderComposer(); };
      wrap.append(reply);
    }
    const line = el('div', 'roof-discussion-input-line');
    const input = el('textarea', 'roof-discussion-input');
    input.placeholder = 'Комментарий'; input.rows = 1;
    const send = el('button', 'roof-discussion-send'); send.type = 'button'; send.innerHTML = icon('send');
    const submit = async() => {
      const text = input.value.trim(); if(!text) return;
      send.disabled = true;
      try {
        await roofTransport.invoke('roof.sendPostComment', {channel_id: channelId, post_id: postId, message: text, reply_to: replyTo?.id || 0});
        replyTo = null;
        await refresh();
      } finally { send.disabled = false; }
    };
    send.onclick = () => void submit();
    input.onkeydown = (event) => {
      if(event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(); }
    };
    line.append(input, send); wrap.append(line); composer.append(wrap); input.focus();
  };

  try { await refresh(); } catch(error) {
    console.error('Roof discussion load failed', error);
    scroll.innerHTML = '<div class="roof-discussion-empty"><strong>Не удалось открыть комментарии</strong></div>';
  }
}

function escapeHtml(value: string): string {
  const div = document.createElement('div'); div.textContent = value; return div.innerHTML;
}

export function installRoofChannelComments(chat: RoofChatLike): void {
  if(!chat || instances.has(chat as object)) return;
  const container = chat.container;
  if(!container) return;
  let timer = 0;
  const schedule = (force = false) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(async() => {
      const channelId = channelIdOf(chat);
      if(force && channelId) settingsCache.delete(channelId);
      await decorate(chat);
    }, 70);
  };
  const observer = new MutationObserver(() => schedule());
  observer.observe(container, {childList: true, subtree: true});
  instances.set(chat as object, observer);
  (window as any).__roofCurrentChat = chat;
  schedule(true);

  roofTransport.onUpdate((update: any) => {
    const channelId = channelIdOf(chat);
    if(update?._ === 'roofUpdateChatSettings' && Number(update.chat_id) === channelId) {
      settingsCache.delete(channelId);
      schedule(true);
    }
    if(Number(update?.channel_id) === channelId && Number(update?.post_id)) {
      if(typeof update.count === 'number') updateFooterCount(channelId, Number(update.post_id), Number(update.count));
      if(activePanel && activePanel.channelId === channelId && activePanel.postId === Number(update.post_id)) void activePanel.refresh();
    }
  });
}
