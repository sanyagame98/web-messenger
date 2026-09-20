import InputSearch from '@components/inputSearch';
import Row from '@components/row';
import SliderSuperTab from '@components/sliderTab';
import appSidebarLeft from '@components/sidebarLeft';
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

type Found = {users?: RoofUser[]};

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

function initials(user: RoofUser) {
  const name = `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username || '?';
  return name.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || '').join('');
}

class RoofNewChatTab extends SliderSuperTab {
  private inputSearch: InputSearch;
  private results: HTMLElement;
  private hint: HTMLElement;
  private generation = 0;

  public async init() {
    this.title.textContent = 'Новый чат';
    this.container.classList.add('roof-native-new-chat-tab');

    this.inputSearch = new InputSearch({
      debounceTime: 180,
      noPlaceholderAnimation: true,
      onChange: (value) => void this.search(value)
    });
    this.inputSearch.input.placeholder = '@username';
    this.inputSearch.input.setAttribute('aria-label', 'Поиск пользователя по username');

    const searchSection = nativeSection();
    searchSection.container.classList.add('roof-native-search-section');
    searchSection.content.append(this.inputSearch.container);

    this.hint = document.createElement('div');
    this.hint.className = 'roof-native-tab-hint';
    this.hint.textContent = 'Найди пользователя по @username';

    this.results = document.createElement('div');
    this.results.className = 'roof-native-rows';

    this.scrollable.append(searchSection.container, this.hint, this.results);
    setTimeout(() => this.inputSearch.input.focus(), 20);
  }

  protected onCloseAfterTimeout() {
    this.inputSearch?.remove();
    super.onCloseAfterTimeout();
  }

  private async search(value: string) {
    const query = value.trim().replace(/^@+/, '');
    const current = ++this.generation;
    this.results.replaceChildren();

    if(query.length < 2) {
      this.hint.textContent = query ? 'Введи минимум 2 символа username' : 'Найди пользователя по @username';
      this.hint.classList.remove('hide');
      return;
    }

    this.hint.textContent = 'Поиск…';
    this.hint.classList.remove('hide');
    try {
      const found = await roofTransport.invoke<Found>('contacts.search', {q: `@${query}`, limit: 30});
      if(current !== this.generation) return;
      const users = Array.isArray(found?.users) ? found.users : [];
      if(!users.length) {
        this.hint.textContent = `Пользователь @${query} не найден`;
        return;
      }

      this.hint.classList.add('hide');
      const section = nativeSection();
      users.forEach((user) => section.content.append(this.renderUser(user)));
      this.results.append(section.container);
    } catch(error) {
      if(current !== this.generation) return;
      console.error('Roof username search failed', error);
      this.hint.textContent = 'Ошибка поиска. Попробуй ещё раз.';
    }
  }

  private renderUser(user: RoofUser): HTMLElement {
    const name = `${user.first_name || ''} ${user.last_name || ''}`.trim() || `@${user.username || user.id}`;
    const titleWrap = document.createElement('span');
    titleWrap.className = 'roof-native-peer-title';
    const title = document.createElement('span');
    title.textContent = name;
    const status = document.createElement('span');
    status.className = 'roof-new-chat-status hide';
    titleWrap.append(title, status);

    const row = new Row({
      title: titleWrap,
      subtitle: user.username ? `@${user.username}` : `ID ${user.id}`,
      clickable: async() => {
        if(row.freezed) return;
        row.freezed = true;
        try {
          await roofTransport.invoke('roof.openDirectChat', {user_id: user.id});
          await this.close();
          appImManager.setInnerPeer({peerId: Number(user.id).toPeerId(false)});
        } catch(error) {
          row.freezed = false;
          console.error('Roof open direct chat failed', error);
        }
      }
    });

    const avatar = row.createMedia('small');
    avatar.classList.add('roof-native-avatar');
    avatar.textContent = initials(user);

    void mountRoofPeerTitleStatus(status, Number(user.id), 19).then((visible) => {
      status.classList.toggle('hide', !visible);
    }).catch(() => status.classList.add('hide'));

    return row.container;
  }
}

export function openRoofNewChatSearch(): void {
  appSidebarLeft.closeTabsBefore(() => {
    void appSidebarLeft.createTab(RoofNewChatTab).open();
  });
}
