// 数字、金额、时间一律用 Intl 按当前语言格式化；币种来自单价表，不随语言变。
export function money(value: number, currency: string, lang: string): string {
  const loc = lang === "zh" ? "zh-CN" : "en-SG";
  if (currency === "SGD") {   // 统一写成 S$：Intl 在 en-SG 下只显示 "$"，容易误认成美元；币种不随界面语言变
    const n = new Intl.NumberFormat(loc, { maximumFractionDigits: 0 }).format(Math.abs(value));
    return `${value < 0 ? "-" : ""}S$${n}`;
  }
  return new Intl.NumberFormat(loc, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}
export function num(value: number, lang: string, digits = 0): string {
  return new Intl.NumberFormat(lang === "zh" ? "zh-CN" : "en-SG", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}
export function pct(value: number, lang: string, digits = 0): string {
  return new Intl.NumberFormat(lang === "zh" ? "zh-CN" : "en-SG", { style: "percent", maximumFractionDigits: digits }).format(value);
}
/** 相对变化：-29.4 → "▼ 29.4%"；正数 → "▲ 3.1%"（输入是百分数而非小数）。 */
export function delta(pctValue: number, lang: string): string {
  const arrow = pctValue < 0 ? "▼" : pctValue > 0 ? "▲" : "";
  return `${arrow} ${num(Math.abs(pctValue), lang, 1)}%`;
}
/** 分钟（自 08:00）→ 24 小时制 HH:MM，英文界面也不写 AM/PM。 */
export function clock(minutesFrom8: number): string {
  const m = Math.max(0, Math.round(minutesFrom8));
  const h = 8 + Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}
