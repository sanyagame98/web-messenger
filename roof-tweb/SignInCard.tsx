import {createSignal, onMount} from 'solid-js';

import Button from '@components/buttonTsx';
import MediaHeader from '@components/mediaHeader';
import roofTransport from '@lib/roof/roofTransport';

import AuthCard from '@/pages/AuthCard';
import {CardSpec, useAuthFlow} from '@/pages/authFlow';
import styles from '@/pages/authFlow.module.scss';

type Spec = Extract<CardSpec, {name: 'signIn'}>;

type RoofUser = {
  id: number;
  username: string;
  display_name: string;
  is_premium?: boolean;
  is_verified?: boolean;
};

function asTwebUser(user: RoofUser) {
  const pFlags: Record<string, boolean> = {self: true};
  if(user.is_premium) pFlags.premium = true;
  if(user.is_verified) pFlags.verified = true;
  return {
    _: 'user',
    id: user.id,
    access_hash: '0',
    first_name: user.display_name || user.username,
    last_name: '',
    username: user.username,
    usernames: [{_: 'username', username: user.username, pFlags: {active: true}}],
    phone: '',
    photo: {_: 'userProfilePhotoEmpty'},
    status: {_: 'userStatusOnline', expires: Math.floor(Date.now() / 1000) + 60},
    pFlags
  } as any;
}

export default function SignInCard(_props: {spec: Spec}) {
  const {managers, toIm} = useAuthFlow();
  const [email, setEmail] = createSignal('');
  const [password, setPassword] = createSignal('');
  const [registerMode, setRegisterMode] = createSignal(false);
  const [submitting, setSubmitting] = createSignal(false);
  const [error, setError] = createSignal('');

  const submit = async(e?: Event) => {
    e?.preventDefault();
    if(submitting()) return;
    setSubmitting(true);
    setError('');
    try {
      const action = registerMode() ?
        roofTransport.register.bind(roofTransport) :
        roofTransport.login.bind(roofTransport);
      const result = await action(email().trim(), password());
      await managers.apiManager.setUser(asTwebUser(result.user as RoofUser));
      roofTransport.connectUpdates();
      toIm();
    } catch(err: any) {
      setError(err?.message || 'Roof authorization failed');
    } finally {
      setSubmitting(false);
    }
  };

  onMount(() => {
    managers.appStateManager.pushToState('authState', {_: 'authStateSignIn'});
  });

  return (
    <AuthCard
      class={styles.pageSignIn}
      header={
        <MediaHeader>
          <MediaHeader.Sticker
            class={styles.logoContainer}
            size={120}
            element={
              <svg class={styles.logo} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" aria-label="Roof">
                <circle cx="80" cy="80" r="70" fill="currentColor" opacity="0.12"/>
                <path d="M42 96V66L80 38l38 28v30h-18V75L80 60 60 75v21H42Z" fill="currentColor"/>
                <path d="M67 122V88h26v34H67Z" fill="currentColor"/>
              </svg>
            }
          />
          <MediaHeader.Title>Roof</MediaHeader.Title>
          <MediaHeader.Subtitle class="secondary">
            Вход по email и паролю. Никаких Telegram-кодов и номеров телефона.
          </MediaHeader.Subtitle>
        </MediaHeader>
      }
      inputWrapper={false}
    >
      <form class="input-wrapper" onSubmit={submit}>
        <label class="input-field input-field-outline">
          <span class="input-field-border"/>
          <input
            class="input-field-input"
            type="email"
            autocomplete="email"
            placeholder="Email"
            value={email()}
            onInput={(event) => setEmail(event.currentTarget.value)}
            required
          />
        </label>
        <label class="input-field input-field-outline">
          <span class="input-field-border"/>
          <input
            class="input-field-input"
            type="password"
            autocomplete={registerMode() ? 'new-password' : 'current-password'}
            placeholder="Пароль"
            minlength="6"
            value={password()}
            onInput={(event) => setPassword(event.currentTarget.value)}
            required
          />
        </label>
        {error() && <div class="error">{error()}</div>}
        <Button type="submit" disabled={submitting()}>
          {submitting() ? 'Подождите…' : registerMode() ? 'Создать аккаунт Roof' : 'Войти в Roof'}
        </Button>
        <Button
          type="button"
          class="btn-secondary"
          onClick={() => {
            setError('');
            setRegisterMode(!registerMode());
          }}
        >
          {registerMode() ? 'У меня уже есть аккаунт' : 'Регистрация по email'}
        </Button>
      </form>
    </AuthCard>
  );
}
