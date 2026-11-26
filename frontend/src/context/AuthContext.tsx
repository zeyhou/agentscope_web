import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { authApi, type Account, type LoginSession } from '@/api/auth';
import { ApiError, getBaseUrl } from '@/api/client';
import { resetAuthRequests, setAuthAccount, setCsrfToken } from '@/lib/auth-session';
import { queryClient } from '@/lib/query-client';

interface AuthValue {
	user: Account | null;
	loading: boolean;
	error: string;
	refresh: () => Promise<void>;
	login: (username: string, password: string) => Promise<void>;
	logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

/** 清理身份相关缓存和旧版选择记录，业务数据仍保留在后端。 */
function clearUserCache() {
	resetAuthRequests();
	queryClient.clear();
	for (const key of ['username', 'chat_last_agent', 'chat_last_session']) localStorage.removeItem(key);
}

export function AuthProvider({ children }: { children: ReactNode }) {
	const [user, setUser] = useState<Account | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState('');
	const identity = useRef('');
	const generation = useRef(0);
	const channel = useRef<BroadcastChannel | null>(null);

	const clear = useCallback(() => {
		generation.current++;
		identity.current = '';
		clearUserCache();
		setUser(null);
		setError('');
		setLoading(false);
	}, []);

	const apply = useCallback((session: LoginSession) => {
		if (identity.current !== session.user.id) clearUserCache();
		identity.current = session.user.id;
		setAuthAccount(session.user.id, getBaseUrl());
		setCsrfToken(session.csrf_token);
		setUser(session.user);
		setLoading(false);
		setError('');
	}, []);

	const refresh = useCallback(async () => {
		const version = ++generation.current;
		if (!getBaseUrl()) { clear(); return; }
		setLoading(true);
		try {
			const session = await authApi.me();
			if (version === generation.current) apply(session);
		} catch (failure) {
			if (version !== generation.current) return;
			if (failure instanceof ApiError && failure.status === 401) clear();
			else if (!(failure instanceof DOMException && failure.name === 'AbortError')) {
				setError(failure instanceof Error ? failure.message : String(failure));
				setLoading(false);
			}
		}
	}, [apply, clear]);

	useEffect(() => {
		void refresh();
		const expired = () => clear();
		const serverChanged = () => { clear(); void refresh(); };
		window.addEventListener('agentscope:auth-expired', expired);
		window.addEventListener('agentscope:server-changed', serverChanged);
		// 同一浏览器共享 Cookie；通知只触发重新核对身份，不把消息中的用户当作可信身份。
		const broadcast = new BroadcastChannel('agentscope-auth');
		channel.current = broadcast;
		broadcast.onmessage = () => { clear(); void refresh(); };
		return () => {
			// 这是异步请求的版本计数，不是 DOM 引用；卸载时使旧响应失效。
			// eslint-disable-next-line react-hooks/exhaustive-deps
			generation.current++;
			window.removeEventListener('agentscope:auth-expired', expired);
			window.removeEventListener('agentscope:server-changed', serverChanged);
			broadcast.close();
		};
	}, [clear, refresh]);

	const login = useCallback(async (username: string, password: string) => {
		const session = await authApi.login(username, password);
		generation.current++;
		apply(session);
		channel.current?.postMessage('changed');
	}, [apply]);

	const logout = useCallback(async () => {
		// 等待服务端撤销成功，不能在网络失败时显示“已退出”。
		await authApi.logout();
		clear();
		channel.current?.postMessage('changed');
	}, [clear]);

	const value = useMemo(() => ({ user, loading, error, refresh, login, logout }), [user, loading, error, refresh, login, logout]);
	return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
	const value = useContext(AuthContext);
	if (!value) throw new Error('AuthProvider is required');
	return value;
}
