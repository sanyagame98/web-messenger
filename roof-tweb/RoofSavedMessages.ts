import roofTransport from '@lib/roof/roofTransport';
import {wrapTelegramEmojiText} from '@lib/roof/telegramEmojiAtlas';

let active: HTMLElement | null = null;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if(cls) node.className = cls;
  return node;
}

function svg(path: string) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function close() { active?.remove(); active = null; }

function renderText(node: HTMLElement, text: string) {
  try { node.append(wrapTelegramEmojiText(text || '')); }
  catch { node.textContent = text || ''; }
}

export async function openRoofSavedMessages(): Promise<void> {
  close();
  const overlay = el('div', 'roof-saved-overlay');
  const panel = el('section', 'roof-saved-panel');
  const header = el('header', 'roof-saved-header');
  const back = el('button', 'roof-saved-icon'); back.type = 'button'; back.innerHTML = svg('M15 18l-6-6 6-6'); back.onclick = close;
  const titleWrap = el('div', 'roof-saved-title');
  const title = el('strong'); title.textContent = 'Избранное';
  const subtitle = el('span'); subtitle.textContent = 'Saved Messages';
  titleWrap.append(title, subtitle);
  const clear = el('button', 'roof-saved-icon'); clear.type = 'button'; clear.title = 'Очистить'; clear.innerHTML = svg('M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15');
  header.append(back, titleWrap, clear);
  const list = el('div', 'roof-saved-list');
  panel.append(header, list); overlay.append(panel); document.body.append(overlay); active = overlay;

  const load = async() => {
    list.replaceChildren();
    const result = await roofTransport.invoke<any>('roof.getSavedMessages', {limit: 200});
    const messages = result?.messages || [];
    if(!messages.length) {
      const empty = el('div', 'roof-saved-empty');
      empty.innerHTML = `${svg('M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1')}<strong>Здесь пока ничего нет</strong><span>Сохраняй важные сообщения, файлы, фото и ссылки — они появятся здесь.</span>`;
      list.append(empty); return;
    }
    messages.forEach((message: any) => {
      const row = el('article', 'roof-saved-message');
      const body = el('div', 'roof-saved-message-body'); renderText(body, String(message.message || ''));
      const meta = el('div', 'roof-saved-message-meta');
      const source = el('span'); source.textContent = `Чат #${message.roof_source_chat_id || ''}`;
      const remove = el('button', 'roof-saved-remove'); remove.type = 'button'; remove.textContent = 'Убрать';
      remove.onclick = async() => { await roofTransport.invoke('roof.unsaveMessage', {message_id: message.id}); row.remove(); if(!list.children.length) void load(); };
      meta.append(source, remove); row.append(body, meta); list.append(row);
    });
  };
  clear.onclick = async() => { if(!confirm('Очистить Избранное?')) return; await roofTransport.invoke('roof.clearSavedMessages', {}); await load(); };
  await load();
}

export async function saveRoofMessage(messageId: number): Promise<void> {
  await roofTransport.invoke('roof.saveMessage', {message_id: messageId});
}
