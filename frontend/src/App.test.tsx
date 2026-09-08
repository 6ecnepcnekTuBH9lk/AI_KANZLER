import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { ConfigProvider, App as AntApp } from "antd";
import App, { Details, Summary } from "./App";
import { format, isRunning } from "./api";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("Русский интерфейс", () => {
  it("разделяет коммерческий результат, операции и доказательства, поддерживает старые строки", () => {
    const view = render(
      <ConfigProvider>
        <Details
          onClose={() => {}}
          row={{
            article: "6A-TEST",
            status: "ХИТ",
            preliminary_band: "ХИТ",
            operational_state: "ТРЕБУЕТ ПРОВЕРКИ",
            operational_signal: "Проверить размеры",
            season_observation_days: 34,
            forecast: 2.5,
            weekly_actual: [],
            diagnosis: { evidence: [] },
          }}
        />
      </ConfigProvider>,
    );
    for (const heading of [
      "Коммерческий результат",
      "Операционная диагностика",
      "Прогноз",
      "Вторая волна",
      "Доказательства и качество данных",
    ])
      expect(
        screen.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
    expect(screen.getByText("Проверить размеры")).toBeInTheDocument();
    view.rerender(
      <ConfigProvider>
        <Details
          onClose={() => {}}
          row={{ article: "OLD", status: "РИСК", weekly_actual: [] }}
        />
      </ConfigProvider>,
    );
    expect(
      screen.getByText("Нет отдельной оценки в старом запуске"),
    ).toBeInTheDocument();
  });
  it("показывает известный итог, покрытие и управленческий смысл", () => {
    render(
      <ConfigProvider>
        <Summary
          result={{
            summary: {
              count: 338,
              planned_count: 223,
              plan_units: 3611.34,
              coverage: {
                plan_units: { known_sum: 3611.34, known_count: 223 },
              },
            },
            counts: {},
            display_summary: {},
            summary_rows: [
              {
                label: "Известный план",
                value: 3611.34,
                format: "units",
                coverage: "223 / 338 артикулов",
                meaning: "Пропуски не заменены нулём",
              },
            ],
          }}
        />
      </ConfigProvider>,
    );
    expect(screen.getByText("223 / 338 артикулов")).toBeInTheDocument();
    expect(screen.getByText("Пропуски не заменены нулём")).toBeInTheDocument();
    expect(screen.queryByText(/3611,3/)).not.toBeInTheDocument();
  });
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
