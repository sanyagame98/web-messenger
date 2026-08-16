import lottieLoader from '@lib/lottie/lottieLoader';

export type RoofPremiumEmojiItem = {
  id: string;
  name: string;
  member: string;
  status_token: string;
  url: string;
};

export type RoofPremiumEmojiPack = {
  id: string;
  title: string;
  file_name: string;
  count: number;
  emojis: RoofPremiumEmojiItem[];
};

type PacksResponse = {
  packs: RoofPremiumEmojiPack[];
  total_packs: number;
  total_emojis: number;
};

const TOKEN_RE = /\[\[roof-tgs:(pack_[a-f0-9]{12}):(emoji_[a-f0-9]{16})\]\]/gi;
const STATUS_RE = /^roof-tgs:(pack_[a-f0-9]{12}):(emoji_[a-f0-9]{16})$/i;
let packsPromise: Promise<PacksResponse> | undefined;

function authHeaders(): HeadersInit {
  let token = '';
  try {
    token = localStorage.getItem('roof_access_token') || '';
  } catch {}
  return token ? {Authorization: `Bearer ${token}`} : {};
}

export function getRoofPremiumEmojiPacks(force = false): Promise<PacksResponse> {
  if(force) packsPromise = undefined;
  return packsPromise ||= fetch('/api/premium-emoji/packs', {headers: authHeaders()})
  .then(async(response) => {
    if(!response.ok) throw new Error(`Roof premium emoji HTTP ${response.status}`);
    return response.json() as Promise<PacksResponse>;
  })
  .catch((error) => {
    packsPromise = undefined;
    throw error;
  });
}

function itemUrl(packId: string, emojiId: string): string {
  return `/api/premium-emoji/packs/${packId}/items/${emojiId}.tgs`;
}

export async function mountRoofPremiumEmojiAnimation(
  container: HTMLElement,
  url: string,
  size = 44
): Promise<void> {
  lottieLoader.getAnimation(container)?.remove();
  container.classList.remove('roof-premium-emoji-failed');
  container.replaceChildren();
  container.style.width = `${size}px`;
  container.style.height = `${size}px`;
  try {
    const player = await lottieLoader.loadAnimationFromURL({
      container,
      width: size,
      height: size,
      group: 'none',
      autoplay: true,
      loop: true,
      noOffscreen: true
    } as any, url);
    await player.loadPromise;
  } catch(error) {
    container.classList.add('roof-premium-emoji-failed');
    container.textContent = '✦';
    console.warn('Roof premium emoji animation failed', error);
  }
}

export async function mountRoofPremiumEmojiStatus(
  container: HTMLElement,
  status: string,
  size = 36
): Promise<void> {
  lottieLoader.getAnimation(container)?.remove();
  container.replaceChildren();
  const normalized = String(status || '').trim();
  const match = STATUS_RE.exec(normalized);
  if(match) {
    container.classList.add('is-animated');
    await mountRoofPremiumEmojiAnimation(container, itemUrl(match[1], match[2]), size);
    return;
  }
  container.classList.remove('is-animated');
  container.style.width = `${size}px`;
  container.style.height = `${size}px`;
  container.textContent = normalized || '✦';
}

function createAnimatedButton(item: RoofPremiumEmojiItem, onSelect: (item: RoofPremiumEmojiItem) => void) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'roof-premium-emoji-item';
  button.title = item.name;

  const animation = document.createElement('span');
  animation.className = 'roof-premium-emoji-animation';
  button.append(animation);
  void mountRoofPremiumEmojiAnimation(animation, item.url, 46);
  button.addEventListener('click', () => onSelect(item));
  return button;
}

export async function openRoofPremiumEmojiPicker(options: {
  title?: string;
  onSelect: (item: RoofPremiumEmojiItem) => void | Promise<void>;
}): Promise<void> {
  document.querySelector('.roof-premium-emoji-overlay')?.remove();

  const overlay = document.createElement('div');
  overlay.className = 'roof-premium-emoji-overlay';
  const panel = document.createElement('div');
  panel.className = 'roof-premium-emoji-panel';
  overlay.append(panel);

  const header = document.createElement('div');
  header.className = 'roof-premium-emoji-header';
  const heading = document.createElement('div');
  heading.className = 'roof-premium-emoji-heading';
  heading.textContent = options.title || 'Roof Premium Emoji';
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'roof-premium-emoji-close';
  close.textContent = '×';
  close.addEventListener('click', () => overlay.remove());
  header.append(heading, close);

  const tabs = document.createElement('div');
  tabs.className = 'roof-premium-emoji-tabs';
  const content = document.createElement('div');
  content.className = 'roof-premium-emoji-content';
  content.textContent = 'Загрузка коллекций…';
  panel.append(header, tabs, content);
  document.body.append(overlay);
  overlay.addEventListener('click', (event) => {
    if(event.target === overlay) overlay.remove();
  });

  let data: PacksResponse;
  try {
    data = await getRoofPremiumEmojiPacks(true);
  } catch(error) {
    content.textContent = 'Не удалось прочитать premium-emoji-packs';
    console.error(error);
    return;
  }

  if(!data.packs.length) {
    content.innerHTML = '<div class="roof-premium-emoji-empty"><b>Коллекций пока нет</b><span>Положи ZIP с .tgs в premium-emoji-packs и открой окно снова.</span></div>';
    return;
  }

  const renderPack = (pack: RoofPremiumEmojiPack, tab: HTMLButtonElement) => {
    tabs.querySelectorAll('button').forEach((button) => button.classList.toggle('active', button === tab));
    content.replaceChildren();
    const meta = document.createElement('div');
    meta.className = 'roof-premium-emoji-pack-meta';
    meta.textContent = `${pack.title} · ${pack.count}`;
    const grid = document.createElement('div');
    grid.className = 'roof-premium-emoji-grid';
    pack.emojis.forEach((item) => {
      grid.append(createAnimatedButton(item, async(selected) => {
        await options.onSelect(selected);
        overlay.remove();
      }));
    });
    content.append(meta, grid);
  };

  data.packs.forEach((pack, index) => {
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'roof-premium-emoji-tab';
    tab.textContent = pack.title;
    tab.addEventListener('click', () => renderPack(pack, tab));
    tabs.append(tab);
    if(index === 0) renderPack(pack, tab);
  });
}

export function decorateRoofPremiumEmojiTokens(root: ParentNode): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let current: Node | null;
  while((current = walker.nextNode())) {
    const text = current as Text;
    if(text.nodeValue?.includes('[[roof-tgs:')) nodes.push(text);
  }

  nodes.forEach((textNode) => {
    const value = textNode.nodeValue || '';
    TOKEN_RE.lastIndex = 0;
    let match: RegExpExecArray | null;
    let last = 0;
    const fragment = document.createDocumentFragment();
    let found = false;
    while((match = TOKEN_RE.exec(value))) {
      found = true;
      if(match.index > last) fragment.append(value.slice(last, match.index));
      const span = document.createElement('span');
      span.className = 'roof-premium-emoji-inline';
      span.dataset.roofPremiumToken = match[0];
      span.setAttribute('contenteditable', 'false');
      fragment.append(span);
      void mountRoofPremiumEmojiAnimation(span, itemUrl(match[1], match[2]), 28);
      last = match.index + match[0].length;
    }
    if(!found) return;
    if(last < value.length) fragment.append(value.slice(last));
    textNode.replaceWith(fragment);
  });
}

export function roofPremiumEmojiMessageToken(item: RoofPremiumEmojiItem): string {
  return `[[${item.status_token}]]`;
}
