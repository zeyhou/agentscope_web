import { useTranslation } from '@/i18n/useI18n';

interface Props {
	resource: { hub_id?: string | null; url?: string | null };
}

/** Glama 要求展示目录数据的页面可见署名，每条资源提供原始条目回链。 */
export function MCPSourceCredit({ resource }: Props) {
	const { t } = useTranslation();
	if (resource.hub_id !== 'glama') return null;
	return (
		<span className="inline-flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
			<a href="https://glama.ai" target="_blank" rel="noopener noreferrer"
				className="underline underline-offset-2" onClick={(event) => event.stopPropagation()}>
				{t('mcp.glamaCredit')}
			</a>
			{resource.url && (
				<a href={resource.url} target="_blank" rel="noopener noreferrer"
					className="underline underline-offset-2" onClick={(event) => event.stopPropagation()}>
					{t('mcp.glamaListing')}
				</a>
			)}
		</span>
	);
}
