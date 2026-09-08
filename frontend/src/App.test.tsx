import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { ConfigProvider, App as AntApp } from "antd";
import App, { Details } from "./App";
import { format, isRunning } from "./api";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("Русский интерфейс", () => {
  it("открывает оба реальных модуля без будущих заглушек", () => {
    render(
      <ConfigProvider>
        <AntApp>
          <App />
        </AntApp>
      </ConfigProvider>,
    );
    expect(
      screen.getByRole("button", { name: "Открыть аналитику" }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Открыть классификацию" }),
    );
    expect(
      screen.getByRole("heading", { name: "Классификация ТН ВЭД" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(
      screen.getByRole("button", { name: /Запустить классификацию/ }),
    ).toBeDisabled();
    expect(
      screen.queryByText("Мониторинг конкурентов"),
    ).not.toBeInTheDocument();
  });
  it("сохраняет различие нуля и отсутствующих показателей", () => {
    expect(format(null)).toBe("—");
    expect(format(0)).toBe("0");
    expect(format(0.85, "execution")).toMatch(/85/);
    expect(isRunning(null)).toBe(false);
  });
  it("показывает причины и verdict кандидатов без финального кода", () => {
    render(
      <ConfigProvider>
        <Details
          onClose={() => {}}
          row={{
            article: "TEST",
            name: "Джемпер",
            code: null,
            status: "Требуется уточнение",
            comment: "Не указана плотность вязки.",
            features: {
              kind: "джемпер",
              gender: "мужской",
              age: "взрослый",
              knit: true,
              material: "хлопок",
              main_text: "100% хлопок",
              details: {},
            },
            missing_input: ["12 петель по горизонтали"],
            missing_rule: [],
            candidates: [
              {
                code: "6110201000",
                verdict: "unresolved",
                description: "Легкий тонкий джемпер",
                missing_input: ["Плотность вязки"],
                conditions: [
                  { verdict: "unresolved", condition: "Измерение плотности" },
                ],
              },
            ],
          }}
        />
      </ConfigProvider>,
    );
    expect(screen.getByText("6110201000 — UNRESOLVED")).toBeInTheDocument();
    expect(screen.getByText("12 петель по горизонтали")).toBeInTheDocument();
    expect(screen.getByText("Код не подтверждён")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "6110201000" })).toHaveAttribute(
      "href",
      "https://www.alta.ru/tnved/code/6110201000/",
    );
  });
});
