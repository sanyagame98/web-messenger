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
import ButtonIcon from '@components/buttonIcon';
import rootScope from '@lib/rootScope';
import Row from '@components/rowTsx';
import Section from '@components/section';
import {renderPeerProfile} from '@components/peerProfile';
import SolidJSHotReloadGuardProvider from '@lib/solidjs/hotReloadGuardProvider';
import {attachClickEvent} from '@helpers/dom/clickEvent';
import showLogOutPopup from '@components/popups/logOut';
import {useSuperTab} from '@components/solidJsTabs/superTabProvider';

const Settings = () => {
  const [tab] = useSuperTab();
  const [premium, setPremium] = createSignal(false);
  const [stars, setStars] = createSignal(0);
  const [status, setStatus] = createSignal('');

  const editBtn = ButtonIcon('edit');
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
    ['unmute', 'Уведомления и звук', AppNotificationsTab],
    ['data', 'Данные и память', AppDataAndStorageTab],
    ['lock', 'Конфиденциальность', AppPrivacyAndSecurityTab],
    ['settings', 'Общие настройки', AppGeneralSettingsTab],
    ['folder', 'Папки с чатами', AppChatFoldersTab],
    ['stickers_face', 'Стикеры и эмодзи', AppStickersAndEmojiTab],
    ['videocamera', 'Звук и камера', AppSpeakersAndCameraTab]
  ] as const;

  return (
    <>
      {peerProfileElement}
      <Section>
        <div class="profile-buttons">
          <For each={rows}>
            {(item) => (
              <Row clickable={() => tab.slider.createTab(item[2] as any).open()}>
                <Row.Icon icon={item[0] as Icon} />
                <Row.Title>{item[1]}</Row.Title>
              </Row>
            )}
          </For>
          <Row clickable={() => tab.slider.createTab(AppLanguageTab).open()}>
            <Row.Icon icon="language" />
            <Row.Title titleRight={<span>Русский</span>} titleRightSecondary>Язык</Row.Title>
          </Row>
          <Row clickable={() => tab.slider.createTab(AppKeyboardShortcutsTab).open()}>
            <Row.Icon icon="keyboard" />
            <Row.Title>Сочетания клавиш</Row.Title>
          </Row>
        </div>
      </Section>

      <Section>
        <div class="roof-premium-card">
          <div class="roof-premium-mark">★</div>
          <div class="roof-premium-copy">
            <div class="roof-premium-title">Roof Premium</div>
            <div class="roof-premium-subtitle">
              {premium() ? `Premium активен${status() ? ` · статус ${status()}` : ''}` : 'Расширенные возможности Roof'}
            </div>
          </div>
          <div class="roof-premium-state">{premium() ? 'Активен' : 'Roof'}</div>
        </div>
        <Row clickable={() => tab.slider.createTab(AppEditProfileTab).open(getEditProfileInitArgs(true))}>
          <Row.Icon icon="star" class="row-icon-premium-color" />
          <Row.Title titleRight={<span>{stars()}</span>} titleRightSecondary>Roof Stars</Row.Title>
        </Row>
        <Row clickable={() => tab.slider.createTab(AppEditProfileTab).open(getEditProfileInitArgs(true))}>
          <Row.Icon icon="stickers_face" />
          <Row.Title titleRight={<span>{status() || 'Добавить'}</span>} titleRightSecondary>Premium эмодзи-статус</Row.Title>
        </Row>
      </Section>
    </>
  );
};

export default Settings;
