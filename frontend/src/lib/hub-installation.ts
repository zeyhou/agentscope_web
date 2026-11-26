/** 市场资源由来源和卡片 ID 唯一确定，不能按名称判断是否安装。 */
export function sourceKey(hubId: string, cardId: string): string {
	return JSON.stringify([hubId, cardId]);
}

interface SourceRecord {
	hub_id: string | null;
	card_id: string | null;
}

/** SkillHub 和 MCPHub 共用身份判断；手动创建的资源不匹配市场卡片。 */
export function installedSourceKeys(records: SourceRecord[]): Set<string> {
	return new Set(
		records.flatMap((record) =>
			record.hub_id && record.card_id ? [sourceKey(record.hub_id, record.card_id)] : [],
		),
	);
}
