import {openRoofSavedMessages, saveRoofMessage} from '@lib/roof/RoofSavedMessages';

type ChatLike = {container?: HTMLElement};
const installed = new WeakSet<object>();

function bookmarkSvg() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z"/></svg>';
}

export function installRoofSavedMessagesHooks(chat: ChatLike): void {
  if(!chat || installed.has(chat as object) || !chat.container) return;
  installed.add(chat as object);
  const container = chat.container;

  const ensureShortcut = () => {
    if(document.querySelector('.roof-saved-shortcut')) return;
    const sidebar = document.querySelector<HTMLElement>('.sidebar-left, #column-left, .tabs-container');
    if(!sidebar) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'roof-saved-shortcut';
    button.innerHTML = `${bookmarkSvg()}<span>Избранное</span>`;
    button.onclick = () => void openRoofSavedMessages();
    sidebar.prepend(button);
  };
  ensureShortcut();
  new MutationObserver(ensureShortcut).observe(document.body, {childList: true, subtree: true});

  container.addEventListener('contextmenu', (event) => {
    const bubble = (event.target as HTMLElement).closest<HTMLElement>('[data-mid], .bubble');
    if(!bubble) return;
    const messageId = Number(bubble.dataset.mid || bubble.getAttribute('data-mid') || 0);
    if(!messageId) return;
    window.setTimeout(() => {
      const menu = document.querySelector<HTMLElement>('.btn-menu.active, .contextmenu, .context-menu');
      if(!menu || menu.querySelector('.roof-save-message-action')) return;
      const action = document.createElement('button');
      action.type = 'button';
      action.className = 'roof-save-message-action';
      action.innerHTML = `${bookmarkSvg()}<span>Сохранить в Избранное</span>`;
      action.onclick = async(e) => { e.preventDefault(); e.stopPropagation(); await saveRoofMessage(messageId); menu.remove(); };
      menu.append(action);
    }, 0);
  }, true);
}
