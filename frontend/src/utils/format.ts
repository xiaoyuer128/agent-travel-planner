// 展示格式化工具函数

export function money(x: number): string {
  return `¥${x.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

/** 从 ISO 时间字符串提取 HH:mm */
export function tTime(iso: string): string {
  return iso.includes("T") ? iso.split("T")[1].slice(0, 5) : iso;
}

/** 将星级数字转为 ★☆ 字符串 */
export function stars(n: number): string {
  const v = Math.max(0, Math.min(5, Math.round(n)));
  return "★".repeat(v) + "☆".repeat(5 - v);
}