import assert from 'node:assert/strict';
import test from 'node:test';

import './load-api.mjs';
const { asrApi } = await import('../src/api/asr.ts');
const { knowledgeBaseApi } = await import('../src/api/knowledgeBase.ts');

test('authenticated document downloads use a proxy URL without a legacy token', () => {
	assert.equal(
		knowledgeBaseApi.documentContentUrl('kb', 'doc', true),
		'https://app.example.test/api/knowledge_bases/kb/documents/doc?download=true',
	);
});

test('ASR sends a real multipart body with the original recording', async (t) => {
	const file = new File(['test-audio'], 'note.wav', { type: 'audio/wav' });
	t.mock.method(globalThis, 'fetch', async (url, options) => {
		assert.equal(url.pathname, '/api/asr/transcriptions');
		assert.equal(options.headers['Content-Type'], undefined);
		assert.ok(options.body instanceof FormData);
		assert.equal(await options.body.get('file').text(), 'test-audio');
		assert.equal(options.body.get('credential_id'), 'demo');
		return Response.json({ text: 'transcribed' });
	});
	assert.deepEqual(
		await asrApi.transcribe({ file, credentialId: 'demo', model: 'asr', parameters: {} }),
		{ text: 'transcribed' },
	);
});
