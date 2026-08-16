import roofTransport from '@lib/roof/roofTransport';

type RoofChatLike = {peerId?: any; container?: HTMLElement};
type UploadItem = {file: File; url?: string; kind: 'photo' | 'video' | 'document'};

const installed = new WeakSet<object>();
let activeOverlay: HTMLElement | null = null;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if(className) node.className = className;
  return node;
}

function icon(name: 'attach' | 'close' | 'send' | 'file'): string {
  const paths = {
    attach: '<path d="M21.4 11.6l-8.9 8.9a6 6 0 0 1-8.5-8.5l9.6-9.6a4 4 0 1 1 5.7 5.7l-9.7 9.7a2 2 0 1 1-2.8-2.8l8.9-8.9"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>'
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
}

function classify(file: File): UploadItem['kind'] {
  if(file.type.startsWith('image/') && file.type !== 'image/gif') return 'photo';
  if(file.type.startsWith('video/')) return 'video';
  return 'document';
}

async function inputPeer(chat: RoofChatLike): Promise<any> {
  const peerId = chat.peerId;
  if(!peerId) throw new Error('ROOF_MEDIA_NO_PEER');
  if(peerId.isAnyChat?.()) {
    const chatId = Number(peerId.toChatId?.() || 0);
    const settings = await roofTransport.invoke<any>('roof.getChatSettings', {chat_id: chatId});
    return settings.type === 'channel' ?
      {_: 'inputPeerChannel', channel_id: chatId, access_hash: '0'} :
      {_: 'inputPeerChat', chat_id: chatId};
  }
  return {_: 'inputPeerUser', user_id: Number(peerId), access_hash: '0'};
}

function fileId(): string {
  return `roof-${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

async function videoDetails(file: File): Promise<{w: number; h: number; duration: number}> {
  if(!file.type.startsWith('video/')) return {w: 0, h: 0, duration: 0};
  return new Promise((resolve) => {
    const video = document.createElement('video');
    const url = URL.createObjectURL(file);
    const done = () => {
      const result = {
        w: Math.max(0, video.videoWidth || 0),
        h: Math.max(0, video.videoHeight || 0),
        duration: Math.max(0, Math.round(video.duration || 0))
      };
      URL.revokeObjectURL(url);
      resolve(result);
    };
    video.preload = 'metadata';
    video.onloadedmetadata = done;
    video.onerror = () => { URL.revokeObjectURL(url); resolve({w: 0, h: 0, duration: 0}); };
    video.src = url;
  });
}

async function uploadFile(file: File, onProgress: (value: number) => void): Promise<any> {
  const id = fileId();
  const chunkSize = 512 * 1024;
  const parts = Math.max(1, Math.ceil(file.size / chunkSize));
  for(let index = 0; index < parts; index++) {
    const start = index * chunkSize;
    const end = Math.min(file.size, start + chunkSize);
    const bytes = new Uint8Array(await file.slice(start, end).arrayBuffer());
    await roofTransport.invoke(parts > 1 ? 'upload.saveBigFilePart' : 'upload.saveFilePart', {
      file_id: id,
      file_part: index,
      file_total_parts: parts,
      bytes
    });
    onProgress((index + 1) / parts);
  }

  const input = {_: 'inputFile', id, parts, name: file.name || 'file', md5_checksum: ''};
  const kind = classify(file);
  if(kind === 'photo') {
    return {_: 'inputMediaUploadedPhoto', file: input, pFlags: {}};
  }
  const attributes: any[] = [{_: 'documentAttributeFilename', file_name: file.name || 'file'}];
  if(kind === 'video') {
    const details = await videoDetails(file);
    attributes.push({
      _: 'documentAttributeVideo',
      duration: details.duration,
      w: details.w || 1280,
      h: details.h || 720,
      pFlags: {supports_streaming: true}
    });
  }
  return {
    _: 'inputMediaUploadedDocument',
    file: input,
    mime_type: file.type || 'application/octet-stream',
    attributes,
    pFlags: {}
  };
}

function cleanup(items: UploadItem[]) {
  items.forEach((item) => item.url && URL.revokeObjectURL(item.url));
}

function openPreview(chat: RoofChatLike, files: File[]) {
  activeOverlay?.remove();
  const items: UploadItem[] = files.slice(0, 20).map((file) => ({
    file,
    kind: classify(file),
    url: file.type.startsWith('image/') || file.type.startsWith('video/') ? URL.createObjectURL(file) : undefined
  }));
  if(!items.length) return;

  const overlay = el('div', 'roof-media-preview-overlay');
  const panel = el('div', 'roof-media-preview-panel');
  const header = el('header', 'roof-media-preview-header');
  const title = el('strong'); title.textContent = items.length > 1 ? `Отправить ${items.length} файлов` : 'Отправить файл';
  const close = el('button', 'roof-media-icon'); close.type = 'button'; close.innerHTML = icon('close');
  close.onclick = () => { cleanup(items); overlay.remove(); if(activeOverlay === overlay) activeOverlay = null; };
  header.append(title, close);

  const grid = el('div', `roof-media-preview-grid${items.length === 1 ? ' single' : ''}`);
  items.forEach((item) => {
    const card = el('div', `roof-media-preview-item ${item.kind}`);
    if(item.kind === 'photo' && item.url) {
      const img = el('img'); img.src = item.url; card.append(img);
    } else if(item.kind === 'video' && item.url) {
      const video = el('video'); video.src = item.url; video.muted = true; video.preload = 'metadata'; card.append(video);
      const badge = el('span', 'roof-media-video-badge'); badge.textContent = 'VIDEO'; card.append(badge);
    } else {
      const fileIcon = el('span', 'roof-media-file-icon'); fileIcon.innerHTML = icon('file');
      const name = el('span', 'roof-media-file-name'); name.textContent = item.file.name || 'Файл';
      const size = el('span', 'roof-media-file-size'); size.textContent = formatBytes(item.file.size);
      card.append(fileIcon, name, size);
    }
    grid.append(card);
  });

  const caption = el('textarea', 'roof-media-caption');
  caption.rows = 2;
  caption.maxLength = 4096;
  caption.placeholder = 'Подпись';

  const progress = el('div', 'roof-media-upload-progress');
  const bar = el('span'); progress.append(bar);
  const footer = el('footer', 'roof-media-preview-footer');
  const hint = el('span'); hint.textContent = items.length > 1 ? 'Будет отправлено альбомом' : formatBytes(items[0].file.size);
  const send = el('button', 'roof-media-send'); send.type = 'button'; send.innerHTML = `${icon('send')}<span>Отправить</span>`;
  footer.append(hint, send);

  panel.append(header, grid, caption, progress, footer);
  overlay.append(panel);
  document.body.append(overlay);
  activeOverlay = overlay;

  const upload = async() => {
    send.disabled = true;
    close.disabled = true;
    progress.classList.add('show');
    try {
      const peer = await inputPeer(chat);
      const uploaded: any[] = [];
      for(let index = 0; index < items.length; index++) {
        const media = await uploadFile(items[index].file, (partProgress) => {
          const total = (index + partProgress) / items.length;
          bar.style.width = `${Math.max(1, Math.min(100, total * 100))}%`;
        });
        uploaded.push(media);
      }
      if(uploaded.length === 1) {
        await roofTransport.invoke('messages.sendMedia', {
          peer,
          media: uploaded[0],
          message: caption.value.trim(),
          random_id: fileId()
        });
      } else {
        await roofTransport.invoke('messages.sendMultiMedia', {
          peer,
          multi_media: uploaded.map((media, index) => ({
            _: 'inputSingleMedia',
            media,
            message: index === 0 ? caption.value.trim() : '',
            random_id: fileId()
          }))
        });
      }
      bar.style.width = '100%';
      cleanup(items);
      overlay.remove();
      if(activeOverlay === overlay) activeOverlay = null;
    } catch(error) {
      console.error('Roof media upload failed', error);
      hint.textContent = error instanceof Error ? error.message : 'Ошибка загрузки';
      hint.classList.add('error');
      send.disabled = false;
      close.disabled = false;
    }
  };
  send.onclick = () => void upload();
  caption.onkeydown = (event) => {
    if(event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); void upload(); }
  };
}

function formatBytes(bytes: number): string {
  if(bytes < 1024) return `${bytes} Б`;
  if(bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

export function installRoofMediaUploader(chat: RoofChatLike): void {
  if(!chat || installed.has(chat as object)) return;
  const container = chat.container;
  if(!container) return;
  installed.add(chat as object);

  const fileInput = el('input') as HTMLInputElement;
  fileInput.type = 'file';
  fileInput.multiple = true;
  fileInput.accept = 'image/*,video/*,audio/*,.pdf,.zip,.rar,.7z,.txt,.doc,.docx,.xls,.xlsx,.ppt,.pptx';
  fileInput.hidden = true;
  document.body.append(fileInput);
  fileInput.onchange = () => {
    const files = Array.from(fileInput.files || []);
    fileInput.value = '';
    if(files.length) openPreview(chat, files);
  };

  let attachButton: HTMLButtonElement | null = null;
  const ensureAttach = () => {
    if(attachButton?.isConnected) return;
    const input = container.querySelector<HTMLElement>('.chat-input, .input-message-container, .chat-input-container');
    if(!input) return;
    attachButton = el('button', 'roof-media-attach');
    attachButton.type = 'button';
    attachButton.title = 'Фото, видео или файл';
    attachButton.innerHTML = icon('attach');
    attachButton.onclick = (event) => { event.preventDefault(); event.stopPropagation(); fileInput.click(); };
    input.append(attachButton);
  };
  ensureAttach();
  const observer = new MutationObserver(ensureAttach);
  observer.observe(container, {childList: true, subtree: true});

  let depth = 0;
  const dropOverlay = el('div', 'roof-media-drop-overlay');
  dropOverlay.innerHTML = `${icon('attach')}<strong>Перетащите сюда фото, видео или файлы</strong><span>До 20 файлов за раз</span>`;
  container.append(dropOverlay);

  container.addEventListener('dragenter', (event) => {
    if(!event.dataTransfer?.types.includes('Files')) return;
    event.preventDefault(); depth++; dropOverlay.classList.add('show');
  });
  container.addEventListener('dragover', (event) => {
    if(!event.dataTransfer?.types.includes('Files')) return;
    event.preventDefault(); if(event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  });
  container.addEventListener('dragleave', (event) => {
    event.preventDefault(); depth = Math.max(0, depth - 1); if(!depth) dropOverlay.classList.remove('show');
  });
  container.addEventListener('drop', (event) => {
    if(!event.dataTransfer?.files?.length) return;
    event.preventDefault(); event.stopPropagation(); depth = 0; dropOverlay.classList.remove('show');
    openPreview(chat, Array.from(event.dataTransfer.files));
  });
}
