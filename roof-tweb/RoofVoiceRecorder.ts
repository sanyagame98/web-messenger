import roofTransport from '@lib/roof/roofTransport';

type RoofChatLike = {peerId?: any; container?: HTMLElement};

const installed = new WeakSet<object>();

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if(className) node.className = className;
  return node;
}

function svg(name: 'mic' | 'send' | 'trash'): string {
  const paths = {
    mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/>',
    send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6"/>'
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
}

async function inputPeer(chat: RoofChatLike): Promise<any> {
  const peerId = chat.peerId;
  if(!peerId) throw new Error('ROOF_VOICE_NO_PEER');
  if(peerId.isAnyChat?.()) {
    const chatId = Number(peerId.toChatId?.() || 0);
    const settings = await roofTransport.invoke<any>('roof.getChatSettings', {chat_id: chatId});
    return settings.type === 'channel' ?
      {_: 'inputPeerChannel', channel_id: chatId, access_hash: '0'} :
      {_: 'inputPeerChat', chat_id: chatId};
  }
  return {_: 'inputPeerUser', user_id: Number(peerId), access_hash: '0'};
}

function chooseMime(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
  return candidates.find((value) => MediaRecorder.isTypeSupported?.(value)) || '';
}

async function uploadBlob(blob: Blob): Promise<{file: any; parts: number}> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const chunkSize = 512 * 1024;
  const parts = Math.max(1, Math.ceil(bytes.length / chunkSize));
  const id = `voice-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  for(let index = 0; index < parts; index++) {
    const chunk = bytes.slice(index * chunkSize, Math.min(bytes.length, (index + 1) * chunkSize));
    await roofTransport.invoke('upload.saveBigFilePart', {
      file_id: id,
      file_part: index,
      file_total_parts: parts,
      bytes: chunk
    });
  }
  return {
    parts,
    file: {_: 'inputFileBig', id, parts, name: 'voice.webm'}
  };
}

function formatTime(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}

export function installRoofVoiceRecorder(chat: RoofChatLike): void {
  if(!chat?.container || installed.has(chat as object)) return;
  installed.add(chat as object);

  const findInput = () => chat.container?.querySelector<HTMLElement>('.chat-input, .input-message-container, .input-wrapper');

  const mount = () => {
    const host = findInput();
    if(!host || host.querySelector('.roof-voice-button')) return;

    const button = el('button', 'roof-voice-button');
    button.type = 'button';
    button.title = 'Записать голосовое сообщение';
    button.innerHTML = svg('mic');
    host.append(button);

    button.onclick = async() => {
      if(document.querySelector('.roof-voice-recording')) return;
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}});
      } catch(error) {
        console.error('Roof microphone access failed', error);
        return;
      }

      const mimeType = chooseMime();
      const recorder = new MediaRecorder(stream, mimeType ? {mimeType} : undefined);
      const chunks: BlobPart[] = [];
      const startedAt = performance.now();
      const samples: number[] = [];
      const overlay = el('div', 'roof-voice-recording');
      const cancel = el('button', 'roof-voice-cancel');
      cancel.type = 'button'; cancel.innerHTML = svg('trash');
      const pulse = el('span', 'roof-voice-dot');
      const timer = el('span', 'roof-voice-time'); timer.textContent = '0:00';
      const wave = el('canvas', 'roof-voice-live-wave'); wave.width = 180; wave.height = 34;
      const send = el('button', 'roof-voice-send'); send.type = 'button'; send.innerHTML = svg('send');
      overlay.append(cancel, pulse, timer, wave, send);
      host.append(overlay);
      button.classList.add('hide');

      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser(); analyser.fftSize = 256;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const ctx = wave.getContext('2d');
      let animation = 0;
      let timerHandle = 0;

      const draw = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for(const value of data) peak = Math.max(peak, Math.abs(value - 128));
        samples.push(Math.max(1, Math.min(255, peak * 2)));
        if(samples.length > 180) samples.shift();
        if(ctx) {
          ctx.clearRect(0, 0, wave.width, wave.height);
          const values = samples.slice(-60);
          values.forEach((value, index) => {
            const h = Math.max(2, (value / 255) * 28);
            ctx.fillRect(index * 3, (wave.height - h) / 2, 2, h);
          });
        }
        animation = requestAnimationFrame(draw);
      };
      draw();
      timerHandle = window.setInterval(() => timer.textContent = formatTime((performance.now() - startedAt) / 1000), 250);

      const cleanup = () => {
        cancelAnimationFrame(animation);
        clearInterval(timerHandle);
        stream.getTracks().forEach((track) => track.stop());
        void audioContext.close();
        overlay.remove();
        button.classList.remove('hide');
      };

      recorder.ondataavailable = (event) => { if(event.data.size) chunks.push(event.data); };
      recorder.start(250);

      cancel.onclick = () => {
        recorder.onstop = cleanup;
        if(recorder.state !== 'inactive') recorder.stop(); else cleanup();
      };

      send.onclick = () => {
        send.disabled = true;
        recorder.onstop = async() => {
          try {
            const duration = Math.max(1, Math.round((performance.now() - startedAt) / 1000));
            const blob = new Blob(chunks, {type: recorder.mimeType || 'audio/webm'});
            const uploaded = await uploadBlob(blob);
            const waveform = samples.length ? samples.filter((_, index) => index % Math.max(1, Math.floor(samples.length / 64)) === 0).slice(0, 64) : [16, 22, 18, 28];
            await roofTransport.invoke('messages.sendMedia', {
              peer: await inputPeer(chat),
              media: {
                _: 'inputMediaUploadedDocument',
                file: uploaded.file,
                mime_type: blob.type || 'audio/webm',
                attributes: [
                  {_: 'documentAttributeFilename', file_name: 'voice.webm'},
                  {_: 'documentAttributeAudio', duration, waveform, pFlags: {voice: true}}
                ],
                pFlags: {}
              },
              message: ''
            });
          } catch(error) {
            console.error('Roof voice send failed', error);
          } finally {
            cleanup();
          }
        };
        if(recorder.state !== 'inactive') recorder.stop();
      };
    };
  };

  const observer = new MutationObserver(mount);
  observer.observe(chat.container, {childList: true, subtree: true});
  mount();
}
