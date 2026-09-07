import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { ConfigProvider, App as AntApp } from "antd";
import App from "./App";
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
});
