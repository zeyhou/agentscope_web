import { ChevronLeft, ChevronRight, Download, Loader2 } from 'lucide-react';
import { getDocument, GlobalWorkerOptions, type PDFDocumentLoadingTask, type PDFDocumentProxy, type RenderTask } from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { useEffect, useRef, useState } from 'react';

import { client } from '@/api/client';
import type { KnowledgeDocumentView } from '@/api/types';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/useI18n';

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

interface Props {
	knowledgeBaseId: string;
	document: KnowledgeDocumentView;
	onDownload: () => void;
}

/** Render inside the page: native embedded PDF readers can remain blank in browsers. */
export default function PdfPreview({ knowledgeBaseId, document, onDownload }: Props) {
	const { t } = useTranslation();
	const containerRef = useRef<HTMLDivElement>(null);
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
	const [page, setPage] = useState(1);
	const [paintedPage, setPaintedPage] = useState(0);
	const [pageText, setPageText] = useState('');
	const [error, setError] = useState('');

	useEffect(() => {
		let cancelled = false;
		let task: PDFDocumentLoadingTask | undefined;
		const controller = new AbortController();
		async function load() {
			try {
				const response = await client.stream(`/knowledge_bases/${knowledgeBaseId}/documents/${document.id}`, { signal: controller.signal });
				const data = new Uint8Array(await response.arrayBuffer());
				if (cancelled) return;
				const base = import.meta.env.BASE_URL;
				task = getDocument({ data, cMapUrl: `${base}pdfjs/cmaps/`, cMapPacked: true, standardFontDataUrl: `${base}pdfjs/standard_fonts/`, wasmUrl: `${base}pdfjs/wasm/`, iccUrl: `${base}pdfjs/iccs/` });
				const loaded = await task.promise;
				if (!cancelled) setPdf(loaded);
			} catch (failure) {
				if (!cancelled) setError(failure instanceof Error ? failure.message : String(failure));
			}
		}
		void load();
		return () => {
			cancelled = true;
			controller.abort();
			void task?.destroy();
		};
	}, [knowledgeBaseId, document.id]);

	useEffect(() => {
		if (!pdf) return;
		let cancelled = false;
		let render: RenderTask | undefined;
		let generation = 0;
		let previousWidth = 0;
		async function paint(width: number) {
			const version = ++generation;
			render?.cancel();
			setPaintedPage(0);
			setPageText('');
			setError('');
			try {
				const pdfPage = await pdf!.getPage(page);
				if (cancelled || version !== generation) return;
				const canvas = canvasRef.current!;
				const viewport = pdfPage.getViewport({ scale: width / pdfPage.getViewport({ scale: 1 }).width });
				const ratio = Math.min(window.devicePixelRatio || 1, 2);
				canvas.width = Math.ceil(viewport.width * ratio);
				canvas.height = Math.ceil(viewport.height * ratio);
				render = pdfPage.render({ canvas, viewport, transform: [ratio, 0, 0, ratio, 0, 0], background: '#fff' });
				await render.promise;
				const text = await pdfPage.getTextContent();
				const renderedText = text.items.map(item => 'str' in item ? item.str : '').join(' ');
				if (cancelled || version !== generation) return;
				setPageText(renderedText);
				setPaintedPage(page);
			} catch (failure) {
				if (!cancelled && version === generation) setError(failure instanceof Error ? failure.message : String(failure));
			}
		}
		const observer = new ResizeObserver(entries => {
			const width = Math.floor(entries[0].contentRect.width);
			if (width > 0 && width !== previousWidth) {
				previousWidth = width;
				void paint(width);
			}
		});
		observer.observe(containerRef.current!);
		return () => { cancelled = true; observer.disconnect(); render?.cancel(); };
	}, [pdf, page, knowledgeBaseId, document.id]);

	return <div className="flex flex-col gap-3">
		<div className="flex flex-wrap items-center justify-between gap-2">
			<div className="flex items-center gap-2">
				<Button variant="outline" size="sm" disabled={!pdf || page === 1} onClick={() => setPage(value => value - 1)} aria-label={t('knowledge.documentDetail.previousPage')}><ChevronLeft className="size-4" /></Button>
				<span className="text-muted-foreground text-xs" aria-live="polite">{pdf ? t('knowledge.documentDetail.pageIndicator', { page, pageCount: pdf.numPages }) : t('common.loading')}</span>
				<Button variant="outline" size="sm" disabled={!pdf || page === pdf.numPages} onClick={() => setPage(value => value + 1)} aria-label={t('knowledge.documentDetail.nextPage')}><ChevronRight className="size-4" /></Button>
			</div>
			<Button variant="outline" size="sm" onClick={onDownload}><Download className="size-3.5" />{t('knowledge.documentDetail.downloadButton')}</Button>
		</div>
		{error && <p role="alert" className="text-destructive break-words text-sm">{error}</p>}
		{!error && paintedPage !== page && <Loader2 aria-label={t('common.loading')} className="mx-auto size-4 animate-spin" />}
		<div ref={containerRef} className="min-w-0 w-full">
			<canvas ref={canvasRef} role="img" aria-label={`${document.filename} · ${page}`} data-testid="pdf-page" data-rendered-page={paintedPage} className="h-auto w-full rounded border bg-white" />
			<p className="sr-only" data-testid="pdf-page-text">{pageText}</p>
		</div>
	</div>;
}
