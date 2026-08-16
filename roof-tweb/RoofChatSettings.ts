import roofTransport from '@lib/roof/roofTransport';

type AdminRights = Record<string, boolean>;
type MemberRow = {
  user: any;
  role: 'owner' | 'admin' | 'member';
  rights: AdminRights;
  rank: string;
};
type ChatSettings = {
  id: number;
  type: 'group' | 'channel';
  title: string;
  avatar_url?: string | null;
  about: string;
  username?: string | null;
  is_public: boolean;
  invite_link: string;
  hide_members: boolean;
  history_visible: boolean;
  posting_mode: 'all' | 'admins';
  comments_enabled: boolean;
  my_role: string;
  can_manage: boolean;
  is_owner: boolean;
  members: MemberRow[];
};

const RIGHTS: Array<[string, string]> = [
  ['change_info', 'Изменять профиль чата'],
  ['delete_messages', 'Удалять сообщения'],
  ['pin_messages', 'Закреплять сообщения'],
  ['invite_users', 'Приглашать пользователей'],
  ['ban_users', 'Блокировать участников'],
  ['post_messages', 'Публиковать сообщения'],
  ['edit_messages', 'Редактировать сообщения'],
  ['add_admins', 'Назначать администраторов'],
  ['manage_call', 'Управлять голосовым чатом']
];

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if(className) node.className = className;
  return node;
}

function svg(name: 'close' | 'copy' | 'refresh' | 'camera' | 'trash' | 'leave'): string {
  const paths = {
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    refresh: '<path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5"/>',
    camera: '<path d="M14.5 4l1.5 2H20a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l1.5-2h5z"/><circle cx="12" cy="13" r="4"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6"/>',
    leave: '<path d="M10 17l5-5-5-5M15 12H3M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/>'
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
}

async function invoke<T = any>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  return roofTransport.invoke<T>(method, params);
}

function field(label: string, value = '', textarea = false) {
  const wrap = el('label', 'roof-chat-settings-field');
  const caption = el('span', 'roof-chat-settings-label');
  caption.textContent = label;
  const input = textarea ? el('textarea', 'roof-chat-settings-input') : el('input', 'roof-chat-settings-input');
  input.value = value;
  wrap.append(caption, input);
  return {wrap, input};
}

function toggle(label: string, checked: boolean) {
  const row = el('label', 'roof-chat-settings-toggle');
  const text = el('span');
  text.textContent = label;
  const input = el('input') as HTMLInputElement;
  input.type = 'checkbox';
  input.checked = checked;
  const slider = el('span', 'roof-chat-settings-switch');
  row.append(text, input, slider);
  return {row, input};
}

function toast(text: string) {
  let node = document.querySelector('.roof-chat-settings-toast') as HTMLElement | null;
  if(!node) {
    node = el('div', 'roof-chat-settings-toast');
    document.body.append(node);
  }
  node.textContent = text;
  node.classList.add('show');
  window.setTimeout(() => node?.classList.remove('show'), 1800);
}

async function uploadAvatar(file: File): Promise<string> {
  const form = new FormData();
  form.append('file', file);
  const token = localStorage.getItem('roof_access_token') || '';
  const response = await fetch('/api/files/image', {
    method: 'POST',
    headers: token ? {Authorization: `Bearer ${token}`} : {},
    body: form
  });
  if(!response.ok) throw new Error(`Avatar upload ${response.status}`);
  const data = await response.json();
  return String(data.url || '');
}

export async function openRoofChatSettings(chatId: number): Promise<void> {
  document.querySelector('.roof-chat-settings-overlay')?.remove();

  const overlay = el('div', 'roof-chat-settings-overlay');
  const panel = el('div', 'roof-chat-settings-panel');
  overlay.append(panel);
  document.body.append(overlay);

  const header = el('div', 'roof-chat-settings-header');
  const close = el('button', 'roof-chat-settings-icon');
  close.type = 'button';
  close.innerHTML = svg('close');
  close.onclick = () => overlay.remove();
  const title = el('div', 'roof-chat-settings-heading');
  title.textContent = 'Настройки Roof';
  header.append(close, title);
  panel.append(header);

  const body = el('div', 'roof-chat-settings-body');
  body.innerHTML = '<div class="roof-chat-settings-loading">Загрузка…</div>';
  panel.append(body);

  overlay.addEventListener('click', (event) => {
    if(event.target === overlay) overlay.remove();
  });

  let data: ChatSettings;
  try {
    data = await invoke<ChatSettings>('roof.getChatSettings', {chat_id: chatId});
  } catch(error) {
    body.innerHTML = '<div class="roof-chat-settings-loading">Не удалось открыть настройки</div>';
    console.error(error);
    return;
  }

  const render = (settings: ChatSettings) => {
    data = settings;
    body.replaceChildren();

    const profile = el('section', 'roof-chat-settings-section roof-chat-settings-profile');
    const avatarWrap = el('div', 'roof-chat-settings-avatar');
    if(settings.avatar_url) {
      const image = el('img');
      image.src = settings.avatar_url;
      avatarWrap.append(image);
    } else {
      avatarWrap.textContent = (settings.title || 'R').slice(0, 1).toUpperCase();
    }
    const avatarButton = el('button', 'roof-chat-settings-avatar-edit');
    avatarButton.type = 'button';
    avatarButton.innerHTML = svg('camera');
    const fileInput = el('input') as HTMLInputElement;
    fileInput.type = 'file';
    fileInput.accept = 'image/png,image/jpeg,image/webp,image/gif';
    fileInput.hidden = true;
    avatarButton.onclick = () => fileInput.click();
    fileInput.onchange = async() => {
      const file = fileInput.files?.[0];
      if(!file) return;
      try {
        avatarButton.disabled = true;
        const url = await uploadAvatar(file);
        render(await invoke<ChatSettings>('roof.updateChatSettings', {chat_id: chatId, avatar_url: url}));
        toast('Аватар сохранён');
      } catch(error) {
        console.error(error);
        toast('Ошибка загрузки аватара');
      } finally {
        avatarButton.disabled = false;
      }
    };
    avatarWrap.append(avatarButton, fileInput);

    const profileFields = el('div', 'roof-chat-settings-profile-fields');
    const titleField = field(settings.type === 'channel' ? 'Название канала' : 'Название группы', settings.title);
    const aboutField = field('Описание', settings.about || '', true);
    const saveMain = el('button', 'roof-chat-settings-primary');
    saveMain.type = 'button';
    saveMain.textContent = 'Сохранить';
    saveMain.onclick = async() => {
      try {
        saveMain.disabled = true;
        render(await invoke<ChatSettings>('roof.updateChatSettings', {
          chat_id: chatId,
          title: titleField.input.value,
          about: aboutField.input.value
        }));
        toast('Изменения сохранены');
      } catch(error) {
        console.error(error);
        toast('Не удалось сохранить');
      } finally {
        saveMain.disabled = false;
      }
    };
    profileFields.append(titleField.wrap, aboutField.wrap, saveMain);
    profile.append(avatarWrap, profileFields);
    body.append(profile);

    const privacy = el('section', 'roof-chat-settings-section');
    const privacyTitle = el('h3');
    privacyTitle.textContent = 'Тип и доступ';
    privacy.append(privacyTitle);

    if(settings.type === 'channel') {
      const publicToggle = toggle('Публичный канал', settings.is_public);
      const usernameField = field('@username', settings.username || '');
      usernameField.wrap.classList.toggle('hide', !settings.is_public);
      publicToggle.input.onchange = () => usernameField.wrap.classList.toggle('hide', !publicToggle.input.checked);
      const savePrivacy = el('button', 'roof-chat-settings-secondary');
      savePrivacy.type = 'button';
      savePrivacy.textContent = 'Применить';
      savePrivacy.onclick = async() => {
        try {
          render(await invoke<ChatSettings>('roof.updateChatSettings', {
            chat_id: chatId,
            is_public: publicToggle.input.checked,
            username: usernameField.input.value
          }));
          toast('Тип канала обновлён');
        } catch(error) {
          console.error(error);
          toast('Username занят или некорректен');
        }
      };
      privacy.append(publicToggle.row, usernameField.wrap, savePrivacy);
    }

    const invite = el('div', 'roof-chat-settings-invite');
    const inviteValue = el('code');
    inviteValue.textContent = settings.invite_link;
    const copy = el('button', 'roof-chat-settings-icon');
    copy.type = 'button';
    copy.innerHTML = svg('copy');
    copy.onclick = async() => {
      await navigator.clipboard?.writeText(settings.invite_link);
      toast('Ссылка скопирована');
    };
    const reset = el('button', 'roof-chat-settings-icon');
    reset.type = 'button';
    reset.innerHTML = svg('refresh');
    reset.title = 'Создать новую ссылку';
    reset.onclick = async() => {
      if(!confirm('Старая ссылка перестанет быть основной. Создать новую?')) return;
      render(await invoke<ChatSettings>('roof.resetInviteLink', {chat_id: chatId}));
      toast('Новая invite-ссылка создана');
    };
    invite.append(inviteValue, copy, reset);
    privacy.append(invite);
    body.append(privacy);

    const permissions = el('section', 'roof-chat-settings-section');
    const permissionTitle = el('h3');
    permissionTitle.textContent = 'Разрешения';
    const hideMembers = toggle('Скрыть список участников', settings.hide_members);
    const history = toggle('История видна новым участникам', settings.history_visible);
    const posting = toggle('Писать могут только администраторы', settings.posting_mode === 'admins');
    const controls = [hideMembers.row, history.row, posting.row];
    let comments: ReturnType<typeof toggle> | undefined;
    if(settings.type === 'channel') {
      comments = toggle('Комментарии под публикациями', settings.comments_enabled);
      controls.push(comments.row);
      posting.input.checked = true;
      posting.input.disabled = true;
    }
    controls.forEach((node) => permissions.append(node));
    const savePermissions = el('button', 'roof-chat-settings-secondary');
    savePermissions.type = 'button';
    savePermissions.textContent = 'Сохранить разрешения';
    savePermissions.onclick = async() => {
      render(await invoke<ChatSettings>('roof.updateChatSettings', {
        chat_id: chatId,
        hide_members: hideMembers.input.checked,
        history_visible: history.input.checked,
        posting_mode: posting.input.checked ? 'admins' : 'all',
        ...(comments ? {comments_enabled: comments.input.checked} : {})
      }));
      toast('Разрешения сохранены');
    };
    permissions.append(savePermissions);
    body.append(permissions);

    const members = el('section', 'roof-chat-settings-section');
    const membersHeader = el('div', 'roof-chat-settings-section-title');
    const membersTitle = el('h3');
    membersTitle.textContent = settings.type === 'channel' ? `Подписчики · ${settings.members.length}` : `Участники · ${settings.members.length}`;
    membersHeader.append(membersTitle);
    members.append(membersHeader);

    if(!settings.members.length && settings.hide_members && !settings.can_manage) {
      const hidden = el('div', 'roof-chat-settings-muted');
      hidden.textContent = 'Список участников скрыт администраторами';
      members.append(hidden);
    }

    settings.members.forEach((member) => {
      const row = el('div', 'roof-chat-member');
      const avatar = el('div', 'roof-chat-member-avatar');
      const user = member.user || {};
      avatar.textContent = String(user.first_name || user.username || '?').slice(0, 1).toUpperCase();
      const info = el('div', 'roof-chat-member-info');
      const name = el('strong');
      name.textContent = String(user.first_name || user.username || 'User');
      const username = el('span');
      username.textContent = user.username ? `@${user.username}` : member.role;
      info.append(name, username);
      const role = el('span', `roof-chat-member-role ${member.role}`);
      role.textContent = member.role === 'owner' ? 'Владелец' : member.role === 'admin' ? (member.rank || 'Админ') : 'Участник';
      row.append(avatar, info, role);

      if(settings.is_owner && member.role !== 'owner') {
        const actions = el('div', 'roof-chat-member-actions');
        const admin = el('button', 'roof-chat-settings-mini');
        admin.type = 'button';
        admin.textContent = member.role === 'admin' ? 'Права' : 'Сделать админом';
        admin.onclick = () => openRights(member);
        const remove = el('button', 'roof-chat-settings-mini danger');
        remove.type = 'button';
        remove.textContent = 'Удалить';
        remove.onclick = async() => {
          if(!confirm(`Удалить @${user.username || user.id} из чата?`)) return;
          render(await invoke<ChatSettings>('roof.removeMember', {chat_id: chatId, user_id: user.id}));
          toast('Участник удалён');
        };
        actions.append(admin, remove);
        row.append(actions);
      }
      members.append(row);
    });
    body.append(members);

    const danger = el('section', 'roof-chat-settings-section roof-chat-settings-danger');
    const dangerTitle = el('h3');
    dangerTitle.textContent = 'Управление чатом';
    danger.append(dangerTitle);
    if(!settings.is_owner) {
      const leave = el('button', 'roof-chat-settings-danger-btn');
      leave.type = 'button';
      leave.innerHTML = `${svg('leave')}<span>Покинуть ${settings.type === 'channel' ? 'канал' : 'группу'}</span>`;
      leave.onclick = async() => {
        if(!confirm('Покинуть этот чат?')) return;
        await invoke('roof.leaveChat', {chat_id: chatId});
        overlay.remove();
        location.reload();
      };
      danger.append(leave);
    } else {
      const deleteBtn = el('button', 'roof-chat-settings-danger-btn');
      deleteBtn.type = 'button';
      deleteBtn.innerHTML = `${svg('trash')}<span>Удалить чат навсегда</span>`;
      deleteBtn.onclick = async() => {
        if(!confirm(`Удалить «${settings.title}» навсегда? Это действие нельзя отменить.`)) return;
        await invoke('roof.deleteChat', {chat_id: chatId});
        overlay.remove();
        location.reload();
      };
      danger.append(deleteBtn);
    }
    body.append(danger);
  };

  const openRights = (member: MemberRow) => {
    const modal = el('div', 'roof-chat-rights-overlay');
    const card = el('div', 'roof-chat-rights-card');
    const heading = el('h3');
    heading.textContent = `Права · @${member.user.username || member.user.id}`;
    const enabled = toggle('Администратор', member.role === 'admin');
    card.append(heading, enabled.row);
    const checks: Record<string, HTMLInputElement> = {};
    RIGHTS.forEach(([key, label]) => {
      const item = toggle(label, Boolean(member.rights?.[key]));
      checks[key] = item.input;
      card.append(item.row);
    });
    const rankField = field('Подпись администратора', member.rank || 'Admin');
    card.append(rankField.wrap);
    const footer = el('div', 'roof-chat-rights-footer');
    const cancel = el('button', 'roof-chat-settings-secondary');
    cancel.type = 'button';
    cancel.textContent = 'Отмена';
    cancel.onclick = () => modal.remove();
    const save = el('button', 'roof-chat-settings-primary');
    save.type = 'button';
    save.textContent = 'Сохранить';
    save.onclick = async() => {
      const rights: AdminRights = {};
      Object.entries(checks).forEach(([key, input]) => rights[key] = input.checked);
      try {
        const updated = await invoke<ChatSettings>('roof.setMemberAdmin', {
          chat_id: chatId,
          user_id: member.user.id,
          enabled: enabled.input.checked,
          rank: rankField.input.value,
          rights
        });
        modal.remove();
        render(updated);
        toast('Права обновлены');
      } catch(error) {
        console.error(error);
        toast('Не удалось изменить права');
      }
    };
    footer.append(cancel, save);
    card.append(footer);
    modal.append(card);
    document.body.append(modal);
    modal.onclick = (event) => { if(event.target === modal) modal.remove(); };
  };

  render(data);
}
