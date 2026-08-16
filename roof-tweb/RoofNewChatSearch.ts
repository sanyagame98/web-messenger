import appImManager from '@lib/appImManager';
import roofTransport from '@lib/roof/roofTransport';
import {mountRoofPeerTitleStatus} from '@lib/roof/RoofPremiumEmojiPacks';

type RoofUser = {
  _: 'user';
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  pFlags?: {premium?: boolean; verified?: boolean};
};

type Found = {
  users?: RoofUser[];
};

let activeOverlay: HTMLElement | undefined;

function initials(user: RoofUser) {
  const name = `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username || '?';
  return name.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || '').join('');
}

function close() {
  activeOverlay?.remove();
  activeOverlay = undefined;
}

function renderUser(user: RoofUser): HTMLButtonElement {
  const row = document.createElement('button');
  row.type = 'button';
  row.className = 'roof-new-chat-user';

  const avatar = document.createElement('span');
  avatar.className = 'roof-new-chat-avatar';
  avatar.textContent = initials(user);

  const copy = document.createElement('span');
  copy.className = 'roof-new-chat-copy';
  const titleLine = document.createElement('span');
  titleLine.className = 'roof-new-chat-title-line';
  const title = document.createElement('span');
  title.className = 'roof-new-chat-title';
  title.textContent = `${user.first_name || ''} ${user.last_name || ''}`.trim() || `@${user.username || user.id}`;
  const status = document.createElement('span');
  status.className = 'roof-new-chat-status hide';
  titleLine.append(title, status);

  const username = document.createElement('span');
  username.className = 'roof-new-chat-username';
  username.textContent = user.username ? `@${user.username}` : `ID ${user.id}`;
  copy.append(titleLine, username);
  row.append(avatar, copy);

  void mountRoofPeerTitleStatus(status, Number(user.id), 19).then((visible) => {
    status.classList.toggle('hide', !visible);
  }).catch(() => status.classList.add('hide'));

  row.addEventListener('click', async() => {
    if(row.classList.contains('is-loading')) return;
    row.classList.add('is-loading');
    try {
      await roofTransport.invoke('roof.openDirectChat', {user_id: user.id});
      close();
      appImManager.setInnerPeer({peerId: Number(user.id).toPeerId(false)});
    } catch(error) {
      row.classList.remove('is-loading');
      console.error('Roof open direct chat failed', error);
      const old = username.textContent;
      username.textContent = 'Не удалось открыть чат';
      setTimeout(() => username.textContent = old, 1600);
    }
  });
  return row;
}

export function openRoofNewChatSearch(): void {
  close();

  const overlay = document.createElement('div');
  overlay.className = 'roof-new-chat-overlay';
  const panel = document.createElement('div');
  panel.className = 'roof-new-chat-panel';

  const header = document.createElement('div');
  header.className = 'roof-new-chat-header';
  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'roof-new-chat-back';
  closeButton.setAttribute('aria-label', 'Закрыть');
  closeButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5 8 12l7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const heading = document.createElement('div');
  heading.className = 'roof-new-chat-heading';
  heading.textContent = 'Новый чат';
  header.append(closeButton, heading);

  const searchWrap = document.createElement('label');
  searchWrap.className = 'roof-new-chat-search';
  searchWrap.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m16.3 16.3 4.2 4.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  const input = document.createElement('input');
  input.type = 'text';
  input.autocomplete = 'off';
  input.spellcheck = false;
  input.placeholder = '@username';
  input.setAttribute('aria-label', 'Поиск по username');
  searchWrap.append(input);

  const hint = document.createElement('div');
  hint.className = 'roof-new-chat-hint';
  hint.textContent = 'Найди пользователя по @username';
  const results = document.createElement('div');
  results.className = 'roof-new-chat-results';
  panel.append(header, searchWrap, hint, results);
  overlay.append(panel);
  document.body.append(overlay);
  activeOverlay = overlay;

  closeButton.addEventListener('click', close);
  overlay.addEventListener('click', (event) => {
    if(event.target === overlay) close();
  });
  const onKey = (event: KeyboardEvent) => {
    if(event.key === 'Escape') {
      close();
      document.removeEventListener('keydown', onKey);
    }
  };
  document.addEventListener('keydown', onKey);

  let generation = 0;
  let timer: number | undefined;
  const search = async() => {
    const query = input.value.trim().replace(/^@+/, '');
    const current = ++generation;
    results.replaceChildren();
    if(query.length < 2) {
      hint.textContent = query ? 'Введи минимум 2 символа username' : 'Найди пользователя по @username';
      hint.classList.remove('hide');
      return;
    }
    hint.textContent = 'Поиск…';
    hint.classList.remove('hide');
    try {
      const found = await roofTransport.invoke<Found>('contacts.search', {q: `@${query}`, limit: 30});
      if(current !== generation) return;
      const users = Array.isArray(found?.users) ? found.users : [];
      if(!users.length) {
        hint.textContent = `Пользователь @${query} не найден`;
        return;
      }
      hint.classList.add('hide');
      results.append(...users.map(renderUser));
    } catch(error) {
      if(current !== generation) return;
      console.error('Roof username search failed', error);
      hint.textContent = 'Ошибка поиска. Попробуй ещё раз.';
    }
  };

  input.addEventListener('input', () => {
    if(timer) clearTimeout(timer);
    timer = window.setTimeout(() => void search(), 180);
  });
  setTimeout(() => input.focus(), 20);
}
