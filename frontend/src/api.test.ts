import { afterEach, expect, it, vi } from "vitest";
import { allRows } from "./api";
afterEach(() => vi.restoreAllMocks());
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
