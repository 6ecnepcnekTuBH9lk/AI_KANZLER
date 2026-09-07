export type DataRow = Record<string, any>;
export type Job = {
  id: string;
  module: "merchandise" | "tnved";
  title: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  message: string;
  created_at: string;
  files: { name: string }[];
  error?: { message: string; details?: { needs?: string[] } };
  result?: DataRow;
  output_name?: string;
};
export async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      data.message || data.detail || `Ошибка запроса (${response.status})`,
    );
  }
  return response.json();
}
export const stateNames: Record<string, string> = {
  queued: "В очереди",
  running: "Выполняется",
  completed: "Готово",
  failed: "Ошибка",
};
export const isRunning = (job?: Job | null) =>
  !!job && ["queued", "running"].includes(job.status);
export async function allRows<T = DataRow>(
  url: string,
  pageSize = 1000,
): Promise<T[]> {
  const rows: T[] = [];
  let total = Infinity;
  while (rows.length < total) {
    const page = await api<{ items: T[]; total: number }>(
      `${url}?limit=${pageSize}&offset=${rows.length}`,
    );
    total = page.total;
    if (!page.items.length && rows.length < total)
      throw new Error(
        "Не удалось загрузить все строки результата. Обновите раздел.",
      );
    rows.push(...page.items);
  }
  return rows;
}
export function format(value: unknown, key = ""): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (typeof value === "number")
    return new Intl.NumberFormat("ru-RU", {
      maximumFractionDigits: 1,
      style: percentKeys.has(key) ? "percent" : "decimal",
    }).format(value);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value))
    return value.split("-").reverse().join(".");
  return String(value);
}
export const percentKeys = new Set([
  "target",
  "plan_pct",
  "st",
  "execution",
  "wow",
  "pace_ratio",
  "forecast_st",
  "size_availability",
  "broken_ratio",
  "warehouse_share",
  "distribution",
  "discount",
  "margin",
  "first_st",
]);
