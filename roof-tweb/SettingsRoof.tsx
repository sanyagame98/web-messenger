import {createSignal, For, onMount} from 'solid-js';
import ButtonMenuToggle from '@components/buttonMenuToggle';
import {
  AppChatFoldersTab,
  AppDataAndStorageTab,
  AppGeneralSettingsTab,
  AppKeyboardShortcutsTab,
  AppLanguageTab,
  AppNotificationsTab,
  AppPrivacyAndSecurityTab,
  AppSpeakersAndCameraTab,
  AppStickersAndEmojiTab
} from '@components/solidJsTabs/tabs';
import {
  AppEditProfileTab,
  getEditProfileInitArgs
} from '@components/solidJsTabs';
import ButtonIcon from '@components/buttonIcon';
import rootScope from '@lib/rootScope';
import Row from '@components/rowTsx';
import Section from '@components/section';
import {renderPeerProfile} from '@components/peerProfile';
import SolidJSHotReloadGuardProvider from '@lib/solidjs/hotReloadGuardProvider';
import {attachClickEvent} from '@helpers/dom/clickEvent';
import showLogOutPopup from '@components/popups/logOut';
import PopupPremium from '@components/popups/premium';
import {useSuperTab} from '@components/solidJsTabs/superTabProvider';

const Settings = () => {
  const [tab] = useSuperTab();
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

  const loadRoofExtras = () => (tab.managers.apiManager as any)
  .invokeApi('roof.getOwnProfile', {})
  .then((data: any) => {
    setStars(Number(data?.stars || 0));
    setStatus(String(data?.emoji_status || ''));
  })
  .catch(() => {});

  const openEditProfile = () => {
    tab.slider.createTab(AppEditProfileTab).open(getEditProfileInitArgs(true));
  };

  onMount(() => {
    tab.container.classList.add('settings-container', 'roof-settings-native');
    tab.header.append(editBtn, btnMenu);
    loadRoofExtras();
  });

  attachClickEvent(editBtn, openEditProfile, {listenerSetter: tab.listenerSetter});

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
          <Row clickable={openEditProfile}>
            <Row.Icon icon="edit" />
            <Row.Title>Редактировать профиль</Row.Title>
          </Row>

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
            <Row.Title>Язык</Row.Title>
          </Row>

          <Row clickable={() => tab.slider.createTab(AppKeyboardShortcutsTab).open()}>
            <Row.Icon icon="keyboard" />
            <Row.Title>Сочетания клавиш</Row.Title>
          </Row>
        </div>
      </Section>

      <Section>
        <Row clickable={() => PopupPremium.show()}>
          <Row.Icon icon="star" class="row-icon-premium-color" />
          <Row.Title>Roof Premium</Row.Title>
        </Row>

        <Row>
          <Row.Icon icon="star" class="row-icon-stars-color" />
          <Row.Title titleRight={<span>{stars()}</span>} titleRightSecondary>
            Roof Stars
          </Row.Title>
        </Row>

        <Row clickable={openEditProfile}>
          <Row.Icon icon="premium_status" />
          <Row.Title titleRight={<span>{status() || 'Добавить'}</span>} titleRightSecondary>
            Premium эмодзи-статус
          </Row.Title>
        </Row>
      </Section>
    </>
  );
};

export default Settings;
