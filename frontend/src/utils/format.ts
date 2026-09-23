/** 字节数格式化：B / KB / MB */
export function formatSize(bytes?: number | null): string {
  if (bytes == null) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

/**
 * 后端 ISO 时间 → 本地可读时间。
 * 说明：MySQL 侧 CURRENT_TIMESTAMP 生成 naive datetime，序列化无时区后缀，
 * 浏览器按本地时区解析——部署机与使用机同为 Asia/Shanghai 时展示一致。
 */
export function formatDateTime(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
