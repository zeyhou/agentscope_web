import { CheckCircle, Download, Loader2, TriangleAlert } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Markdown } from '@/components/markdown';
import { Button } from '@/components/ui/button';
import { parseOfdmReport, reportMarkdownForDisplay, verifyOfdmReport, type OfdmReport } from '@/lib/ofdm-report';

export function OfdmReportCard({ value }: { value: unknown }) {
	const [checked, setChecked] = useState<{ value: unknown; report?: OfdmReport; error?: string }>();
	useEffect(() => {
		let active = true;
		async function check() {
			try {
				const report = parseOfdmReport(value);
				await verifyOfdmReport(report);
				if (active) setChecked({ value, report });
			} catch (error) {
				if (active) setChecked({ value, error: error instanceof Error ? error.message : String(error) });
			}
		}
		void check();
		return () => { active = false; };
	}, [value]);
	const result = checked?.value === value ? checked : undefined;
	const report = result?.report;
	function download() {
		if (!report) return;
		const url = URL.createObjectURL(new Blob([report.approved_report], { type: 'text/markdown;charset=utf-8' }));
		const link = document.createElement('a');
		link.href = url;
		link.download = `ofdm-${report.experiment_binding?.slug ?? 'clarification'}-${report.delivery_id.slice(0, 12)}.md`;
		link.click();
		URL.revokeObjectURL(url);
	}
	return (
		<section aria-label="OFDM 校验报告" className="my-3 w-full min-w-0 rounded-xl border bg-card p-4 text-sm" data-testid="ofdm-report">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<div className="flex items-center gap-2 font-medium">
					{report ? <CheckCircle className="size-4 text-emerald-600" /> : result?.error ? <TriangleAlert className="size-4 text-destructive" /> : <Loader2 className="size-4 animate-spin" />}
					{report ? 'OFDM 报告 · 身份与 SHA-256 校验通过' : result?.error ? '报告校验失败' : '正在校验报告…'}
				</div>
				{report && <Button variant="outline" size="sm" onClick={download}><Download className="size-3.5" />下载原文</Button>}
			</div>
			{result?.error && <p role="alert" className="mt-3 text-destructive">{result.error}</p>}
			{report && <>
				<p className="mt-2 text-muted-foreground">{report.experiment_binding ? `实验：${report.experiment_binding.name}` : '约束澄清报告 · 未执行实验'}</p>
				<details className="mt-2 text-xs text-muted-foreground"><summary className="cursor-pointer">查看校验信息</summary><div className="mt-2 space-y-1 break-all"><p>交付 ID：{report.delivery_id}</p><p>正文 SHA-256：{report.content_sha256}</p><p>报告 ID：{report.report_id}</p><p>来源：MCP 后端原文；平台验证事实、语义与身份，浏览器独立复核正文和身份哈希。</p></div></details>
				<div data-testid="ofdm-report-text" className="mt-4 min-w-0 border-t pt-4 text-sm leading-7">
					<Markdown mode="static" isAnimating={false} className="[&_p]:whitespace-pre-line">
						{reportMarkdownForDisplay(report.approved_report)}
					</Markdown>
				</div>
			</>}
		</section>
	);
}
