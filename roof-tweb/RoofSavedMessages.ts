import Icon from '@components/icon';
import ButtonIcon from '@components/buttonIcon';
import roofTransport from '@lib/roof/roofTransport';
import {wrapTelegramEmojiText} from '@lib/roof/telegramEmojiAtlas';

let active: HTMLElement | null = null;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if(cls) node.className = cls;
  return node;
}

function icon(name: 'back' | 'delete' | 'savedmessages') {
  return Icon(name).outerHTML;
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
  const back = ButtonIcon('back'); back.classList.add('roof-saved-icon'); back.onclick = close;
  const titleWrap = el('div', 'roof-saved-title');
  const title = el('strong'); title.textContent = 'Избранное';
  const subtitle = el('span'); subtitle.textContent = 'Saved Messages';
  titleWrap.append(title, subtitle);
  const clear = ButtonIcon('delete'); clear.classList.add('roof-saved-icon'); clear.title = 'Очистить';
  header.append(back, titleWrap, clear);
  const list = el('div', 'roof-saved-list');
  panel.append(header, list); overlay.append(panel); document.body.append(overlay); active = overlay;

  const load = async() => {
    list.replaceChildren();
    const result = await roofTransport.invoke<any>('roof.getSavedMessages', {limit: 200});
    const messages = result?.messages || [];
    if(!messages.length) {
      const empty = el('div', 'roof-saved-empty');
      empty.innerHTML = `${icon('savedmessages')}<strong>Здесь пока ничего нет</strong><span>Сохраняй важные сообщения, файлы, фото и ссылки — они появятся здесь.</span>`;
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
