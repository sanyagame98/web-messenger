import ButtonIcon from '@components/buttonIcon';
import Icon from '@components/icon';
import Row from '@components/row';
import SliderSuperTab from '@components/sliderTab';
import appSidebarLeft from '@components/sidebarLeft';
import roofTransport from '@lib/roof/roofTransport';
import wrapEmojiText from '@lib/richTextProcessor/wrapEmojiText';

function nativeSection() {
  const container = document.createElement('div');
  container.className = 'sidebar-left-section-container';
  const section = document.createElement('div');
  section.className = 'sidebar-left-section';
  const content = document.createElement('div');
  content.className = 'sidebar-left-section-content';
  section.append(content);
  container.append(section);
  return {container, content};
}

function renderText(text: string): HTMLElement {
  const node = document.createElement('span');
  node.append(wrapEmojiText(text || ''));
  return node;
}

class RoofSavedMessagesTab extends SliderSuperTab {
  private rows: HTMLElement;
  private empty: HTMLElement;
  private clearButton: HTMLButtonElement;

  public async init() {
    this.title.textContent = 'Избранное';
    this.container.classList.add('roof-native-saved-tab');

    this.clearButton = ButtonIcon('delete');
    this.clearButton.title = 'Очистить Избранное';
    this.header.append(this.clearButton);
    this.listenerSetter.add(this.clearButton)('click', () => void this.clear());

    this.rows = document.createElement('div');
    this.rows.className = 'roof-native-rows';

    this.empty = document.createElement('div');
    this.empty.className = 'roof-native-empty';
    this.empty.append(
      Icon('savedmessages', 'roof-native-empty-icon'),
      Object.assign(document.createElement('strong'), {textContent: 'Здесь пока ничего нет'}),
      Object.assign(document.createElement('span'), {
        textContent: 'Сохраняй важные сообщения, файлы, фото и ссылки — они появятся здесь.'
      })
    );

    this.scrollable.append(this.rows, this.empty);
    await this.load();
  }

  private async load() {
    const result = await roofTransport.invoke<any>('roof.getSavedMessages', {limit: 200});
    const messages = result?.messages || [];
    this.rows.replaceChildren();
    this.empty.classList.toggle('hide', !!messages.length);
    this.clearButton.classList.toggle('hide', !messages.length);
    if(!messages.length) return;

    const section = nativeSection();
    messages.forEach((message: any) => {
      const remove = ButtonIcon('delete');
      remove.title = 'Убрать из Избранного';
      const row = new Row({
        title: renderText(String(message.message || 'Сообщение')),
        subtitle: `Чат #${message.roof_source_chat_id || ''}`,
        rightContent: remove,
        noWrap: true
      });
      const media = row.createMedia('small');
      media.append(Icon('savedmessages'));
      media.classList.add('roof-native-saved-media');
      this.listenerSetter.add(remove)('click', async(event) => {
        event.stopPropagation();
        await roofTransport.invoke('roof.unsaveMessage', {message_id: message.id});
        await this.load();
      });
      section.content.append(row.container);
    });
    this.rows.append(section.container);
  }

  private async clear() {
    if(!confirm('Очистить Избранное?')) return;
    await roofTransport.invoke('roof.clearSavedMessages', {});
    await this.load();
  }
}

export function openRoofSavedMessages(): void {
  appSidebarLeft.closeTabsBefore(() => {
    void appSidebarLeft.createTab(RoofSavedMessagesTab).open();
  });
}

export async function saveRoofMessage(messageId: number): Promise<void> {
  await roofTransport.invoke('roof.saveMessage', {message_id: messageId});
}
