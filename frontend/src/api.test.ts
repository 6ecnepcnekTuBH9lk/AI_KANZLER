import { afterEach, expect, it, vi } from "vitest";
import { allRows, displayUnits, format } from "./api";
afterEach(() => vi.restoreAllMocks());
it.each([
  [1.4, "1"],
  [1.5, "2"],
  [2.5, "3"],
  [-1.5, "-2"],
  [null, "—"],
])("округляет физические единицы %s → %s", (raw, expected) => {
  expect(displayUnits(raw as number | null)).toBe(expected);
});
it("сохраняет дробные темпы и проценты, не меняет raw", () => {
  const raw = 1.5;
  expect(format(raw, "forecast")).toBe("2");
  expect(format(raw, "required")).toBe("1,5");
  expect(format(1, "execution")).toMatch(/100,0/);
  expect(raw).toBe(1.5);
});
it("загружает все страницы без скрытого ограничения в 5000 строк", async () => {
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      const offset = Number(
        new URL(String(input), "http://localhost").searchParams.get("offset"),
      );
      return new Response(
        JSON.stringify({
          total: 5001,
          items: Array.from(
            { length: Math.min(1000, 5001 - offset) },
            (_, i) => ({ id: offset + i }),
          ),
        }),
      );
    });
  const rows = await allRows("/rows");
  expect(rows).toHaveLength(5001);
  expect(rows[5000].id).toBe(5000);
  expect(fetcher).toHaveBeenCalledTimes(6);
});
