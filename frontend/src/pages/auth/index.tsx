import { ArrowRight, Eye, EyeOff, Loader2, Settings2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import { SilkBackdrop } from './SilkBackdrop';
import { authApi } from '@/api/auth';
import { getBaseUrl } from '@/api/client';
import AgentScopeMark from '@/assets/images/embodied_waveform_mono.svg?react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/context/AuthContext';
import { useTranslation } from '@/i18n/useI18n';

import './auth.css';

export function AuthPage({ register = false }: { register?: boolean }) {
	const { user, loading, login } = useAuth();
	const { t } = useTranslation();
	const navigate = useNavigate();
	const [username, setUsername] = useState('');
	const [password, setPassword] = useState('');
	const [confirmation, setConfirmation] = useState('');
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState('');
	const [showPassword, setShowPassword] = useState(false);
	if (!getBaseUrl()) return <Navigate to="/setup" replace />;
	if (!loading && user) return <Navigate to="/chat" replace />;

	async function submit(event: FormEvent) {
		event.preventDefault();
		setError('');
		if (register && password !== confirmation) { setError(t('auth.passwordMismatch')); return; }
		setBusy(true);
		try {
			if (register) {
				await authApi.register(username.trim(), password);
				setPassword('');
				setConfirmation('');
				toast.success(t('auth.registered'));
				navigate('/login');
			} else {
				await login(username.trim(), password);
				setPassword('');
				navigate('/chat', { replace: true });
			}
		} catch (failure) {
			setError(failure instanceof Error ? failure.message : String(failure));
		} finally {
			setBusy(false);
		}
	}

	return (
		<main className={`auth-page${register ? ' auth-page-register' : ''}`}>
			<section className="auth-form-panel" aria-labelledby="auth-heading">
				<header className="auth-brand"><AgentScopeMark aria-hidden="true" /><span>Embodied Waveform</span></header>
				<div className="auth-form-body">
					<div className="auth-form-content">
						<div className="auth-heading">
							<h1 id="auth-heading">{t(register ? 'auth.registerTitle' : 'auth.loginTitle')}</h1>
							<p>{t(register ? 'auth.registerDescription' : 'auth.description')}</p>
						</div>
						<form onSubmit={submit} aria-labelledby="auth-heading">
							<FieldGroup className="auth-fields">
								<Field>
									<FieldLabel htmlFor="auth-username">{t('auth.username')}</FieldLabel>
									<Input id="auth-username" autoComplete="username" placeholder={t('auth.usernamePlaceholder')} value={username} onChange={e => setUsername(e.target.value)} minLength={3} maxLength={64} required />
								</Field>
								<Field>
									<FieldLabel htmlFor="auth-password">{t('auth.password')}</FieldLabel>
									<div className="auth-password-field">
										<Input id="auth-password" type={showPassword ? 'text' : 'password'} autoComplete={register ? 'new-password' : 'current-password'} placeholder={t('auth.passwordPlaceholder')} value={password} onChange={e => setPassword(e.target.value)} minLength={register ? 8 : 1} maxLength={128} aria-describedby={register ? 'auth-password-hint' : undefined} required />
										<button type="button" className="auth-password-toggle" aria-label={t(showPassword ? 'auth.hidePassword' : 'auth.showPassword')} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff /> : <Eye />}</button>
									</div>
									{register && <p id="auth-password-hint" className="auth-hint">{t('auth.passwordHint')}</p>}
								</Field>
								{register && <Field>
									<FieldLabel htmlFor="auth-confirm">{t('auth.confirmPassword')}</FieldLabel>
									<Input id="auth-confirm" type={showPassword ? 'text' : 'password'} autoComplete="new-password" placeholder={t('auth.confirmPlaceholder')} value={confirmation} onChange={e => setConfirmation(e.target.value)} minLength={8} maxLength={128} required />
								</Field>}
								{error && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
								<Button type="submit" disabled={busy || loading} className="auth-submit">{busy ? <Loader2 className="size-4 animate-spin" /> : null}{t(register ? 'auth.register' : 'auth.login')}{!busy && <ArrowRight className="size-4" />}</Button>
							</FieldGroup>
						</form>
						<p className="auth-switch"><Link to={register ? '/login' : '/register'}>{t(register ? 'auth.haveAccount' : 'auth.needAccount')}<ArrowRight aria-hidden="true" /></Link></p>
					</div>
				</div>
				<footer className="auth-footer"><Link to="/setup"><Settings2 aria-hidden="true" />{t('auth.serverSettings')}</Link></footer>
			</section>
			<aside className="auth-art-panel" aria-label={t('auth.workspace')}>
				<SilkBackdrop />
				<div className="auth-art-caption">
					<p className="auth-art-label">{t('auth.workspace')}</p>
					<h2>{t('auth.artHeadingFirst')}<br />{t('auth.artHeadingSecond')}</h2>
					<p className="auth-art-description">{t('auth.artDescription')}</p>
				</div>
			</aside>
		</main>
	);
}
