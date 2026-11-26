export function resolveApiUrl(base: string, path: string): URL {
	const url = new URL(base);
	if (
		!['http:', 'https:'].includes(url.protocol) ||
		url.username ||
		url.password ||
		url.search ||
		url.hash
	) {
		throw new TypeError(
			'Enter an HTTP(S) server address without credentials, query or fragment.',
		);
	}
	url.pathname = `${url.pathname.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
	return url;
}
