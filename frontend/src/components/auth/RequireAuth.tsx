import { Loader2 } from 'lucide-react';
import { Navigate } from 'react-router-dom';

import { getBaseUrl } from '@/api/client';
import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import { UploadProvider } from '@/context/UploadContext';
import { useTranslation } from '@/i18n/useI18n';

export function RequireAuth() {
	const { user, loading, error, refresh } = useAuth();
	const { t } = useTranslation();
	if (!getBaseUrl()) return <Navigate to="/setup" replace />;
	if (loading) return <div className="flex h-screen items-center justify-center"><Loader2 className="animate-spin" aria-label={t('common.loading')} /></div>;
	if (error) return <div className="flex h-screen flex-col items-center justify-center gap-4"><p>{error}</p><Button onClick={() => void refresh()}>{t('auth.retry')}</Button><a href="/setup">{t('auth.serverSettings')}</a></div>;
	if (!user) return <Navigate to="/login" replace />;
	// 身份改变时卸载整个业务树，清理消息、预览、语音及上传状态。
	return <UploadProvider key={user.id}><AppLayout /></UploadProvider>;
}
