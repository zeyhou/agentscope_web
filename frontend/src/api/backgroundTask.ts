import { client } from './client';
import type { ListBackgroundTasksResponse } from './types';

export const backgroundTaskApi = {
	list: (sessionId: string, baseUrl: string, signal: AbortSignal) =>
		client.get<ListBackgroundTasksResponse>(
			'/background-tasks',
			{ session_id: sessionId },
			{ baseUrl, signal, silent: true, timeoutMs: 10_000 },
		),
};
