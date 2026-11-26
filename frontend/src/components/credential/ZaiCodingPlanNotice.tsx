import { Info } from 'lucide-react';

import { useTranslation } from '@/i18n/useI18n';

/** 创建、编辑和详情共用中国站提示，避免将智谱 Key 发往国际站。 */
export function ZaiCodingPlanNotice({ type }: { type?: string }) {
	const { t } = useTranslation();
	if (type !== 'zai_coding_credential') return null;

	return (
		<div className="flex gap-2 rounded-lg border bg-muted/40 p-3 text-sm">
			<Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
			<div className="space-y-1">
				<p className="font-medium">{t('credential.zaiCoding.title')}</p>
				<p className="text-muted-foreground">{t('credential.zaiCoding.description')}</p>
				<a
					href="https://bigmodel.cn/apikey/coding-plan-per"
					target="_blank"
					rel="noreferrer"
					className="inline-block underline underline-offset-4"
				>
					{t('credential.zaiCoding.manageKeys')}
				</a>
			</div>
		</div>
	);
}
