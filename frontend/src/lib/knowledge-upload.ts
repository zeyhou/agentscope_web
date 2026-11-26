// 浏览器和操作系统可能遗漏或误报 Office 的 MIME 类型。
// 后端按 MIME 选择解析器，因此上传前统一这些已支持格式的类型。
const DOCUMENT_MIME_TYPES: Record<string, string> = {
	'.csv': 'text/csv',
	'.htm': 'text/html',
	'.html': 'text/html',
	'.json': 'application/json',
	'.markdown': 'text/markdown',
	'.md': 'text/markdown',
	'.rst': 'text/x-rst',
	'.txt': 'text/plain',
	'.xml': 'application/xml',
	'.yaml': 'application/x-yaml',
	'.yml': 'application/x-yaml',
	'.pdf': 'application/pdf',
	'.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
	'.xls': 'application/vnd.ms-excel',
	'.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
	'.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
};

export function normalizeKnowledgeUploadFile(file: File): File {
	const dot = file.name.lastIndexOf('.');
	const type = dot >= 0 ? DOCUMENT_MIME_TYPES[file.name.slice(dot).toLowerCase()] : undefined;
	if (!type || type === file.type) return file;
	// 保留文件名、原始字节及修改时间，仅修正 multipart 中的 Content-Type。
	return new File([file], file.name, { type, lastModified: file.lastModified });
}
