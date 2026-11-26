import { client } from './client';

export interface Account {
	id: string;
	username: string;
	created_at: number;
}

export interface LoginSession {
	user: Account;
	csrf_token: string;
	expires_at: number;
}

export const authApi = {
	me: () => client.get<LoginSession>('/auth/me', undefined, { silent: true }),
	login: (username: string, password: string) =>
		client.post<LoginSession>('/auth/login', { username, password }, undefined, { silent: true }),
	register: (username: string, password: string) =>
		client.post<{ user: Account }>('/auth/register', { username, password }, undefined, { silent: true }),
	logout: () => client.post<void>('/auth/logout', undefined, undefined, { silent: true }),
};
