import { client, type ApiRequestOptions } from './client';
import type { ChatRequest, Msg } from './types';

export interface ChatQueueItem {
	id: string;
	created_at: string;
	input: Msg | Msg[];
	state: 'queued' | 'steering' | 'failed';
	error: string | null;
}

interface ChatQueueResponse {
	items: ChatQueueItem[];
}

const queuePath = (id: string) => `/chat/queue/${encodeURIComponent(id)}`;

/**
 * Chat API — fire-and-forget trigger for chat runs.
 *
 * Events produced by the run are delivered via the session's SSE
 * stream endpoint (``GET /sessions/{sid}/stream``), not in the
 * response body of this POST.
 */
export const chatApi = {
	/**
	 * Trigger a chat run for the specified session.
	 *
	 * Accepts user messages, human-in-the-loop confirmation events,
	 * or ``null`` (continue from current state). Returns immediately;
	 * the caller should already be subscribed to the session's SSE
	 * stream to receive the resulting events.
	 *
	 * @param body - The chat request payload.
	 * @returns A confirmation object ``{ status, session_id }``.
	 */
	trigger: (body: ChatRequest, options?: ApiRequestOptions) =>
		client.post<{
			status: 'started' | 'queued';
			session_id: string;
			queue_item_id: string | null;
		}>('/chat/', body, undefined, options),
	queue: (agentId: string, sessionId: string, silent = false, options?: ApiRequestOptions) =>
		client.get<ChatQueueResponse>(
			'/chat/queue',
			{ agent_id: agentId, session_id: sessionId },
			{ silent, ...options },
		),
	updateQueued: (
		id: string,
		body: { agent_id: string; session_id: string; input: Msg | Msg[] },
	) => client.patch<ChatQueueResponse>(queuePath(id), body),
	deleteQueued: (id: string, agentId: string, sessionId: string, options?: ApiRequestOptions) =>
		client.delete<ChatQueueResponse>(
			queuePath(id),
			{ agent_id: agentId, session_id: sessionId },
			options,
		),
	steerQueued: (id: string, agentId: string, sessionId: string, replyId: string) =>
		client.post<ChatQueueResponse>(`${queuePath(id)}/steer`, {
			agent_id: agentId,
			session_id: sessionId,
			reply_id: replyId,
		}),
	reorderQueued: (agentId: string, sessionId: string, itemIds: string[]) =>
		client.patch<ChatQueueResponse>('/chat/queue/order', {
			agent_id: agentId,
			session_id: sessionId,
			item_ids: itemIds,
		}),
	createSubmission: (agentId: string, sessionId: string, options?: ApiRequestOptions) =>
		client.post<{ submission_id: string; expires_at: number }>(
			'/chat/submissions',
			undefined,
			{ agent_id: agentId, session_id: sessionId },
			options,
		),
	cancelSubmission: (
		id: string,
		agentId: string,
		sessionId: string,
		options?: ApiRequestOptions,
	) =>
		client.post<{
			state: 'cancelled' | 'started' | 'unknown';
			reply_id?: string;
			queue_item_id: string | null;
			before_claim?: boolean;
		}>(
			`/chat/submissions/${encodeURIComponent(id)}/cancel`,
			undefined,
			{ agent_id: agentId, session_id: sessionId },
			options,
		),
};
