import { Info } from 'lucide-react';

import { useTranslation } from '@/i18n/useI18n';

/** 创建、编辑和详情复用厂商提示；模型目录与知识库能力由后端提供。 */
export function SiliconFlowNotice({ type }: { type?: string }) {
	const { t } = useTranslation();
	if (type !== 'siliconflow_credential') return null;
	return (
		<div className="flex gap-2 rounded-lg border bg-muted/40 p-3 text-sm">
			<Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
			<div className="space-y-1">
				<p className="font-medium">{t('credential.siliconflow.title')}</p>
				<p className="text-muted-foreground">{t('credential.siliconflow.description')}</p>
				<a href="https://cloud.siliconflow.cn/account/ak" target="_blank" rel="noreferrer" className="inline-block underline underline-offset-4">{t('credential.siliconflow.manageKeys')}</a>
			</div>
		</div>
	);
}
