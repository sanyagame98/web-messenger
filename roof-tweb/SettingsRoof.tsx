import {createSignal, For, onMount} from 'solid-js';
import ButtonMenuToggle from '@components/buttonMenuToggle';
import {
  AppChatFoldersTab,
  AppDataAndStorageTab,
  AppEditProfileTab,
  AppGeneralSettingsTab,
  AppKeyboardShortcutsTab,
  AppLanguageTab,
  AppNotificationsTab,
  AppPrivacyAndSecurityTab,
  AppSpeakersAndCameraTab,
  AppStickersAndEmojiTab,
  getEditProfileInitArgs
} from '@components/solidJsTabs/tabs';
import rootScope from '@lib/rootScope';
import Row from '@components/rowTsx';
import Section from '@components/section';
import {renderPeerProfile} from '@components/peerProfile';
import SolidJSHotReloadGuardProvider from '@lib/solidjs/hotReloadGuardProvider';
import {attachClickEvent} from '@helpers/dom/clickEvent';
import showLogOutPopup from '@components/popups/logOut';
import {useSuperTab} from '@components/solidJsTabs/superTabProvider';

const ICONS: Record<string, string> = {
  notifications: '<path d="M12 22a2.5 2.5 0 0 0 2.35-1.65h-4.7A2.5 2.5 0 0 0 12 22Zm7-5.5-1.7-2.1V10a5.3 5.3 0 0 0-4.3-5.2V4a1 1 0 1 0-2 0v.8A5.3 5.3 0 0 0 6.7 10v4.4L5 16.5V18h14v-1.5Z"/>',
  data: '<path d="M4 5.5C4 3.57 7.58 2 12 2s8 1.57 8 3.5S16.42 9 12 9 4 7.43 4 5.5Zm0 5C4 12.43 7.58 14 12 14s8-1.57 8-3.5V8.42C18.2 10 15.18 11 12 11s-6.2-1-8-2.58v2.08Zm0 5C4 17.43 7.58 19 12 19s8-1.57 8-3.5v-2.08C18.2 15 15.18 16 12 16s-6.2-1-8-2.58v2.08Z"/>',
  lock: '<path d="M7 10V7a5 5 0 0 1 10 0v3h1.5A1.5 1.5 0 0 1 20 11.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 20.5v-9A1.5 1.5 0 0 1 5.5 10H7Zm2 0h6V7a3 3 0 0 0-6 0v3Zm3 4a2 2 0 0 0-1 3.73V20h2v-2.27A2 2 0 0 0 12 14Z"/>',
  settings: '<path d="m19.14 12.94.04-.94-.04-.94 2.03-1.58-2-3.46-2.49 1a7.8 7.8 0 0 0-1.62-.94L14.68 3h-4l-.38 3.08c-.58.24-1.12.55-1.62.94l-2.49-1-2 3.46 2.03 1.58-.04.94.04.94-2.03 1.58 2 3.46 2.49-1c.5.39 1.04.7 1.62.94L10.68 21h4l.38-3.08c.58-.24 1.12-.55 1.62-.94l2.49 1 2-3.46-2.03-1.58ZM12.68 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8Zm0-2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/>',
  folders: '<path d="M3 5a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v11a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V5Zm2 4v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9H5Z"/>',
  emoji: '<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 2a8 8 0 1 1 0 16 8 8 0 0 1 0-16ZM8 8h2v2H8V8Zm6 0h2v2h-2V8Zm-6.5 5h9c-.6 2.1-2.25 3.5-4.5 3.5S8.1 15.1 7.5 13Z"/>',
  camera: '<path d="M3 6.5A2.5 2.5 0 0 1 5.5 4h8A2.5 2.5 0 0 1 16 6.5v2.12l4.2-2.52A1.2 1.2 0 0 1 22 7.13v9.74a1.2 1.2 0 0 1-1.8 1.03L16 15.38v2.12a2.5 2.5 0 0 1-2.5 2.5h-8A2.5 2.5 0 0 1 3 17.5v-11ZM5 7v10a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H6a1 1 0 0 0-1 1Zm11 4v2l4 2.4V8.6L16 11Z"/>',
  language: '<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm6.92 9h-3.05a15.7 15.7 0 0 0-1.2-5.05A8.03 8.03 0 0 1 18.92 11ZM12 4c.88 1.07 1.63 3.38 1.83 7h-3.66C10.37 7.38 11.12 5.07 12 4Zm-2.67 1.95A15.7 15.7 0 0 0 8.13 11H5.08a8.03 8.03 0 0 1 4.25-5.05ZM5.08 13h3.05a15.7 15.7 0 0 0 1.2 5.05A8.03 8.03 0 0 1 5.08 13ZM12 20c-.88-1.07-1.63-3.38-1.83-7h3.66c-.2 3.62-.95 5.93-1.83 7Zm2.67-1.95a15.7 15.7 0 0 0 1.2-5.05h3.05a8.03 8.03 0 0 1-4.25 5.05Z"/>',
  keyboard: '<path d="M3.5 5h17A2.5 2.5 0 0 1 23 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-17A2.5 2.5 0 0 1 1 16.5v-9A2.5 2.5 0 0 1 3.5 5ZM4 8v2h2V8H4Zm4 0v2h2V8H8Zm4 0v2h2V8h-2Zm4 0v2h2V8h-2ZM4 12v2h2v-2H4Zm4 0v2h2v-2H8Zm4 0v2h2v-2h-2Zm4 0v2h4v-2h-4ZM7 16v1h10v-1H7Z"/>',
  star: '<path d="m12 2.6 2.85 5.78 6.38.93-4.62 4.5 1.09 6.35L12 17.16l-5.7 3 1.09-6.35-4.62-4.5 6.38-.93L12 2.6Z"/>',
  edit: '<path d="m16.86 3.49 3.65 3.65L8.65 19H5v-3.65L16.86 3.49Zm0 2.83L7 16.18V17h.82l9.86-9.86-.82-.82Z"/>'
};

const RoofIcon = (props: {name: string, premium?: boolean}) => (
  <span class={`roof-native-icon${props.premium ? ' roof-native-icon-premium' : ''}`} aria-hidden="true">
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" innerHTML={ICONS[props.name] || ICONS.settings} />
  </span>
);

const createRoofHeaderButton = (name: string, label: string) => {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn-icon rp btn-circle roof-header-svg-button';
  button.setAttribute('aria-label', label);
  button.title = label;
  button.innerHTML = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICONS[name] || ICONS.settings}</svg>`;
  return button;
};

const Settings = () => {
  const [tab] = useSuperTab();
  const [premium, setPremium] = createSignal(false);
  const [stars, setStars] = createSignal(0);
  const [status, setStatus] = createSignal('');

  const editBtn = createRoofHeaderButton('edit', 'Редактировать профиль');
  const btnMenu = ButtonMenuToggle({
    listenerSetter: tab.listenerSetter,
    direction: 'bottom-left',
    buttons: [{
      icon: 'logout',
      text: 'EditAccount.Logout',
      onClick: () => showLogOutPopup()
    }]
  });

  onMount(() => {
    tab.container.classList.add('settings-container', 'roof-settings-container');
    tab.header.append(editBtn, btnMenu);
    (tab.managers.apiManager as any).invokeApi('roof.getProfileExtras', {}).then((data: any) => {
      setPremium(!!data?.premium);
      setStars(Number(data?.stars || 0));
      setStatus(String(data?.emoji_status || ''));
    }).catch(() => {});
  });

  attachClickEvent(editBtn, () => {
    tab.slider.createTab(AppEditProfileTab).open(getEditProfileInitArgs(true));
  }, {listenerSetter: tab.listenerSetter});

  const peerProfileElement = renderPeerProfile({
    peerId: rootScope.myId,
    isDialog: false,
    scrollable: tab.scrollable,
    setCollapsedOn: tab.container
  }, SolidJSHotReloadGuardProvider);

  const rows = [
    ['notifications', 'Уведомления и звук', AppNotificationsTab],
    ['data', 'Данные и память', AppDataAndStorageTab],
    ['lock', 'Конфиденциальность', AppPrivacyAndSecurityTab],
    ['settings', 'Общие настройки', AppGeneralSettingsTab],
    ['folders', 'Папки с чатами', AppChatFoldersTab],
    ['emoji', 'Стикеры и эмодзи', AppStickersAndEmojiTab],
    ['camera', 'Звук и камера', AppSpeakersAndCameraTab]
  ] as const;

  return (
    <>
      {peerProfileElement}
      <Section>
        <div class="profile-buttons roof-settings-list">
          <For each={rows}>
            {(item) => (
              <Row clickable={() => tab.slider.createTab(item[2] as any).open()}>
                <RoofIcon name={item[0]} />
                <Row.Title>{item[1]}</Row.Title>
              </Row>
            )}
          </For>
          <Row clickable={() => tab.slider.createTab(AppLanguageTab).open()}>
            <RoofIcon name="language" />
            <Row.Title titleRight={<span>Русский</span>} titleRightSecondary>Язык</Row.Title>
          </Row>
          <Row clickable={() => tab.slider.createTab(AppKeyboardShortcutsTab).open()}>
            <RoofIcon name="keyboard" />
            <Row.Title>Сочетания клавиш</Row.Title>
          </Row>
        </div>
      </Section>

      <Section>
        <div class="roof-premium-card">
          <div class="roof-premium-mark"><RoofIcon name="star" premium /></div>
          <div class="roof-premium-copy">
            <div class="roof-premium-title">Roof Premium</div>
            <div class="roof-premium-subtitle">
              {premium() ? `Premium активен${status() ? ` · статус ${status()}` : ''}` : 'Premium-эмодзи, статусы и расширенные возможности'}
            </div>
          </div>
          <div class="roof-premium-state">{premium() ? 'Активен' : 'Roof'}</div>
        </div>
        <Row clickable={() => tab.slider.createTab(AppEditProfileTab).open(getEditProfileInitArgs(true))}>
          <RoofIcon name="star" premium />
          <Row.Title titleRight={<span>{stars()}</span>} titleRightSecondary>Roof Stars</Row.Title>
        </Row>
        <Row clickable={() => tab.slider.createTab(AppEditProfileTab).open(getEditProfileInitArgs(true))}>
          <RoofIcon name="emoji" />
          <Row.Title titleRight={<span class="roof-current-status">{status() || 'Добавить'}</span>} titleRightSecondary>Premium эмодзи-статус</Row.Title>
        </Row>
      </Section>
    </>
  );
};

export default Settings;
