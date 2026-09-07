import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Layout,
  Menu,
  Progress,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from "antd";
import type { UploadFile } from "antd";
import {
  AppstoreOutlined,
  BarChartOutlined,
  FileExcelOutlined,
  HistoryOutlined,
  SettingOutlined,
  UploadOutlined,
  DownloadOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, allRows, format, isRunning, stateNames } from "./api";
import type { DataRow, Job } from "./api";

const { Title, Text } = Typography;
const tabs = [
  ["summary", "Сводка"],
  ["categories", "Категории"],
  ["articles", "Артикулы"],
  ["weekly-plan", "План по неделям"],
  ["pricing", "Ценовые решения"],
  ["second-wave", "Вторая волна"],
  ["actions", "Действия"],
  ["data-quality", "Качество данных"],
];
const statusColor: Record<string, string> = {
  ХИТ: "green",
  "В ПЛАНЕ": "blue",
  РИСК: "orange",
  АУТСАЙДЕР: "red",
  "НЕДОСТАТОЧНО ДАННЫХ": "default",
  "Код определён": "green",
  "Требуется уточнение": "orange",
  "Техническая ошибка": "red",
};
export function Status({ value }: { value: string }) {
  return (
    <Tag color={statusColor[value] || "default"}>
      {stateNames[value] || value}
    </Tag>
  );
}

function ResultTable({
  rows,
  schema,
  onSelect,
}: {
  rows: DataRow[];
  schema: [string, string][];
  onSelect?: (r: DataRow) => void;
}) {
  const columns = schema.map(([key, label], i) => ({
    title: label,
    dataIndex: key,
    key,
    width: i === 0 ? 175 : typeof rows[0]?.[key] === "number" ? 135 : 210,
    sorter: (a: DataRow, b: DataRow) =>
      typeof a[key] === "number" && typeof b[key] === "number"
        ? a[key] - b[key]
        : String(a[key] ?? "").localeCompare(String(b[key] ?? ""), "ru"),
    render: (v: unknown) =>
      key === "status" ? (
        <Status value={String(v)} />
      ) : (
        <span title={format(v, key)}>
          {format(v, /^\d{4}-\d{2}-\d{2}$/.test(key) ? "st" : key)}
        </span>
      ),
    fixed: i === 0 ? ("left" as const) : undefined,
  }));
  return (
    <Table
      size="small"
      columns={columns}
      dataSource={rows.map((r, i) => ({ ...r, __rowKey: i }))}
      rowKey="__rowKey"
      scroll={{ x: "max-content", y: 520 }}
      pagination={{
        defaultPageSize: 25,
        showSizeChanger: true,
        pageSizeOptions: [25, 50, 100],
        showTotal: (n) => `Строк: ${n}`,
      }}
      onRow={(r) => ({
        onClick: () => onSelect?.(r),
        style: { cursor: onSelect ? "pointer" : "default" },
      })}
      locale={{
        emptyText: <Empty description="Нет строк для выбранных условий" />,
      }}
    />
  );
}

function UploadRun({
  module,
  onCreated,
  disabled,
  needs,
}: {
  module: "merchandise" | "tnved";
  onCreated: (id: string) => void;
  disabled: boolean;
  needs?: string[];
}) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [verify, setVerify] = useState(false);
  const [busy, setBusy] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const { message } = AntApp.useApp();
  async function start() {
    setBusy(true);
    try {
      const form = new FormData();
      files.forEach((f) =>
        form.append(
          module === "tnved" ? "file" : "files",
          f.originFileObj || (f as unknown as Blob),
        ),
      );
      if (module === "tnved") form.append("verify_existing", String(verify));
      else form.append("options", JSON.stringify(overrides));
      const response = await api<{ id: string }>(`/api/${module}/runs`, {
        method: "POST",
        body: form,
      });
      onCreated(response.id);
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const labels: Record<string, string> = {
    season: "Сезон, например ОЗ26",
    control_date: "Контрольная дата, ГГГГ-ММ-ДД",
    season_start: "Начало сезона, ГГГГ-ММ-ДД",
    season_end: "Конец сезона, ГГГГ-ММ-ДД",
  };
  return (
    <Card className="upload-panel">
      <div className="upload-row">
        <div>
          <Text strong>
            {module === "tnved" ? "Исходный Excel" : "Актуальные данные сезона"}
          </Text>
          <p className="muted">
            {module === "tnved"
              ? "Загрузите номенклатуру. Результат сохранит листы, формулы и оформление исходного файла."
              : "Три файла: поартикульный план, план из ценообразования и анализ продаж. Сезон и дата определяются автоматически."}
          </p>
        </div>
        <Upload
          multiple={module === "merchandise"}
          maxCount={module === "tnved" ? 1 : 3}
          accept=".xlsx"
          beforeUpload={() => false}
          fileList={files}
          onChange={(e) => setFiles(e.fileList)}
          disabled={disabled || busy}
        >
          <Button icon={<UploadOutlined />}>Выбрать Excel</Button>
        </Upload>
        <Button
          type="primary"
          onClick={start}
          loading={busy}
          disabled={disabled || files.length !== (module === "tnved" ? 1 : 3)}
        >
          Запустить {module === "tnved" ? "классификацию" : "анализ"}
        </Button>
      </div>
      {module === "tnved" && (
        <Checkbox
          checked={verify}
          onChange={(e) => setVerify(e.target.checked)}
        >
          Проверить и исправить уже заполненные коды
        </Checkbox>
      )}
      {!!needs?.length && (
        <Space wrap className="clarification">
          {needs.map((key) => (
            <Input
              key={key}
              aria-label={labels[key]}
              placeholder={labels[key]}
              value={overrides[key] || ""}
              onChange={(e) =>
                setOverrides({ ...overrides, [key]: e.target.value })
              }
            />
          ))}
        </Space>
      )}
    </Card>
  );
}

function Details({
  row,
  onClose,
}: {
  row: DataRow | null;
  onClose: () => void;
}) {
  if (!row) return null;
  const tnved = "features" in row;
  return (
    <Drawer open title={row.article || row.name} width={820} onClose={onClose}>
      <Status value={row.status} />
      <Title level={5}>{tnved ? row.name : row.category}</Title>
      {tnved ? (
        <>
          <Descriptions
            bordered
            column={1}
            size="small"
            items={[
              { key: "code", label: "Код ТН ВЭД", children: format(row.code) },
              {
                key: "comment",
                label: "Комментарий",
                children: row.comment || "—",
              },
              {
                key: "type",
                label: "Вид изделия",
                children: format(row.features.kind),
              },
              {
                key: "gender",
                label: "Пол",
                children: format(row.features.gender),
              },
              {
                key: "knit",
                label: "Трикотаж",
                children: format(row.features.knit),
              },
              {
                key: "mat",
                label: "Классифицирующий материал",
                children: format(row.features.material),
              },
              {
                key: "comp",
                label: "Основной состав",
                children: row.features.main_text,
              },
              {
                key: "source",
                label: "Подтверждение Alta",
                children: row.evidence ? (
                  <a href={row.evidence.url} target="_blank" rel="noreferrer">
                    {row.evidence.description}
                  </a>
                ) : (
                  "Код не подтверждён"
                ),
              },
            ]}
          />
          {!!row.candidates?.length && (
            <>
              <Title level={5}>Кандидаты для уточнения</Title>
              {row.candidates.map((c: DataRow) => (
                <p key={c.code}>
                  <a
                    href={`https://www.alta.ru/tnved/code/${c.code}/`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {c.code}
                  </a>{" "}
                  — {c.description}
                </p>
              ))}
            </>
          )}
        </>
      ) : (
        <>
          <p>{row.recommendation}</p>
          <Descriptions
            bordered
            column={2}
            items={[
              ["base", "Начальный остаток"],
              ["season_plan", "План сезона, ед."],
              ["plan_units", "План на дату, ед."],
              ["season_fact", "Факт сезона, ед."],
              ["execution", "Выполнение плана"],
              ["preseason", "Предсезон, ед."],
              ["forecast", "Прогноз, ед."],
              ["cover", "Покрытие, недель"],
              ["deadline", "Срок реализации"],
              ["review_date", "Дата проверки"],
            ].map(([key, label]) => ({
              key,
              label,
              children: format(row[key], key),
            }))}
          />
          <Title level={5}>Накопительный план реализации</Title>
          {row.weekly_plan?.length ? (
            <div className="chart">
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={row.weekly_plan}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="week_end" tickFormatter={(v) => format(v)} />
                  <YAxis tickFormatter={(v) => format(v, "st")} />
                  <Tooltip formatter={(v) => format(v, "st")} />
                  <Line
                    dataKey="pct"
                    name="План"
                    stroke="#284a69"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty description="Плановая кривая недоступна" />
          )}
          <Title level={5}>Фактические продажи по неделям</Title>
          <div className="chart">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={row.weekly_actual}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="week_start" tickFormatter={(v) => format(v)} />
                <YAxis />
                <Tooltip />
                <Line
                  dataKey="quantity"
                  name="Продажи, ед."
                  stroke="#487d71"
                  dot={false}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <Title level={5}>Проверки перед ценовым решением</Title>
          <ResultTable
            rows={row.operations || []}
            schema={[
              ["step", "Порядок"],
              ["check", "Проверка"],
              ["confirmed", "Подтверждено"],
            ]}
          />
          <p>{row.pricing?.reason}</p>
          <Title level={5}>Исторический контекст</Title>
          <p>{row.historical_text}</p>
          <Alert
            type="warning"
            title="Качество данных"
            description={row.qa_text || "Ограничений не выявлено"}
          />
        </>
      )}
    </Drawer>
  );
}

function Summary({ result }: { result: DataRow }) {
  const s = result.summary;
  return (
    <>
      <div className="kpi-grid">
        {[
          ["count", "Артикулов"],
          ["base", "Начальный остаток"],
          ["plan_units", "План на дату, ед."],
          ["season_fact", "Факт сезона, ед."],
          ["execution", "Выполнение плана"],
          ["forecast", "Прогноз, ед."],
        ].map(([key, label]) => {
          const incomplete = s[key] == null;
          const coverage =
            key === "execution" ? s.comparable : s.coverage?.[key];
          const count =
            key === "execution" ? coverage?.count : coverage?.known_count;
          const value =
            incomplete && count > 0
              ? key === "execution"
                ? coverage.execution
                : coverage.known_sum
              : s[key];
          return (
            <Card key={key}>
              <Statistic title={label} value={format(value, key)} />
              {incomplete && (
                <Text type="secondary">
                  {count > 0
                    ? `${key === "execution" ? "Сопоставимый набор" : "Доступные данные"}: ${count} из ${s.count} артикулов`
                    : "Недостаточно данных"}
                </Text>
              )}
            </Card>
          );
        })}
      </div>
      <Card title="Статусы коллекции">
        <Space wrap>
          {Object.entries(result.counts).map(([name, count]) => (
            <span key={name}>
              <Status value={name} />
              <strong>{String(count)}</strong>
            </span>
          ))}
        </Space>
        <p className="muted">
          Период плана: {format(result.season_start)} —{" "}
          {format(result.season_end)}. Предсезонные продажи учитываются
          отдельно.
        </p>
        <p className="muted">
          План на дату доступен для {s.planned_count} из {s.count} артикулов.
          Если исходные показатели неполны, общий итог обозначается «—».
        </p>
      </Card>
      <Card title="Расчёт по доступным данным">
        <Space wrap>
          {Object.entries(s.coverage || {}).map(([key, value]) => {
            const c = value as DataRow;
            const labels: Record<string, string> = {
              base: "Начальный остаток",
              plan_units: "План на дату",
              season_fact: "Факт сезона",
              forecast: "Прогноз",
            };
            return (
              <div className="coverage-value" key={key}>
                <Text type="secondary">
                  {labels[key]} · {c.known_count} артикулов
                </Text>
                <div>
                  <strong>{format(c.known_sum)} ед.</strong>
                </div>
              </div>
            );
          })}
        </Space>
        <p>
          Сопоставимый набор: {s.comparable?.count} артикулов с планом и фактом.
          Выполнение: {format(s.comparable?.execution, "execution")}.
        </p>
      </Card>
      <Card title="Управленческая сводка">
        <Descriptions
          bordered
          column={2}
          items={Object.entries(result.display_summary).map(
            ([label, value]) => ({
              key: label,
              label,
              children: format(value),
            }),
          )}
        />
      </Card>
    </>
  );
}

function ModulePage({
  module,
  jobId,
  onCreated,
}: {
  module: "merchandise" | "tnved";
  jobId: string | null;
  onCreated: (id: string) => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [tab, setTab] = useState("summary");
  const [rows, setRows] = useState<DataRow[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<DataRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setJob(null);
    setRows([]);
    setError("");
    if (!jobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const j = await api<Job>(`/api/jobs/${jobId}`);
        if (stopped) return;
        setJob(j);
        if (isRunning(j)) timer = setTimeout(poll, 1200);
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
    }
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jobId]);
  const loadRows = useCallback(async () => {
    if (
      job?.status !== "completed" ||
      (module === "merchandise" && tab === "summary")
    )
      return;
    setLoading(true);
    setError("");
    try {
      setRows(
        await allRows(
          `/api/${module}/runs/${job.id}/${module === "tnved" ? "items" : tab}`,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [job, module, tab]);
  useEffect(() => {
    void loadRows();
  }, [loadRows]);
  const filtered = rows.filter(
    (r) =>
      (!q ||
        Object.values(r).some(
          (v) =>
            typeof v === "string" && v.toLowerCase().includes(q.toLowerCase()),
        )) &&
      (!status || r.status === status),
  );
  let schema: [string, string][] = [];
  if (module === "tnved")
    schema = [
      ["article", "Артикул"],
      ["name", "Наименование"],
      ["code", "Код ТН ВЭД"],
      ["status", "Состояние"],
      ["comment", "Комментарий"],
    ];
  else if (tab === "weekly-plan")
    schema = [
      ["article", "Артикул"],
      ["code", "Код"],
      ["base", "Начальный остаток"],
      ...(job?.result?.week_columns || []).map(
        (w: DataRow) => [w.week_start, w.label] as [string, string],
      ),
    ];
  else schema = job?.result?.schemas?.[tab] || [];
  if (tab === "articles")
    schema = schema.filter(([key]) =>
      [
        "article",
        "category",
        "base",
        "plan_units",
        "season_fact",
        "execution",
        "forecast",
        "stock",
        "status",
        "primary_cause",
      ].includes(key),
    );
  async function select(r: DataRow) {
    if (module === "tnved") {
      setSelected(r);
      return;
    }
    if (r.article && tab !== "data-quality")
      try {
        setSelected(
          await api<DataRow>(
            `/api/merchandise/runs/${jobId}/articles/${encodeURIComponent(r.article)}`,
          ),
        );
      } catch (e) {
        setError((e as Error).message);
      }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <Title level={3}>
            {module === "tnved"
              ? "Классификация ТН ВЭД"
              : "Коммерческая аналитика"}
          </Title>
          <Text type="secondary">
            {module === "tnved"
              ? "Проверка по Alta.ru и заполнение номенклатуры"
              : "План, факт, прогноз и управление ассортиментом"}
          </Text>
        </div>
        {job?.status === "completed" && (
          <Button
            icon={<DownloadOutlined />}
            href={`/api/${module}/runs/${job.id}/export`}
          >
            Скачать Excel
          </Button>
        )}
      </div>
      <UploadRun
        module={module}
        onCreated={onCreated}
        disabled={isRunning(job)}
        needs={job?.error?.details?.needs}
      />
      {error && (
        <Alert
          type="error"
          title={error}
          showIcon
          closable
          onClose={() => setError("")}
        />
      )}
      {job && (
        <Card className="run-status">
          <Space>
            <Status value={job.status} />
            <Text strong>{job.title}</Text>
            <Text type="secondary">{job.message}</Text>
          </Space>
          {isRunning(job) && (
            <Progress percent={job.progress} status="active" />
          )}
        </Card>
      )}
      {job?.status === "failed" && (
        <Alert
          type="error"
          title="Обработка не завершена"
          description={job.error?.message}
          showIcon
        />
      )}
      {job?.status === "completed" && job.result && (
        <>
          {module === "tnved" ? (
            <div className="kpi-grid">
              <Card>
                <Statistic title="Всего товаров" value={job.result.total} />
              </Card>
              {Object.entries(job.result.counts).map(([label, value]) => (
                <Card key={label}>
                  <Statistic title={label} value={Number(value)} />
                </Card>
              ))}
            </div>
          ) : (
            <Tabs
              activeKey={tab}
              onChange={(v) => {
                setRows([]);
                setTab(v);
                setQ("");
                setStatus("");
              }}
              items={tabs.map(([key, label]) => ({ key, label }))}
            />
          )}
          {module === "merchandise" && tab === "summary" ? (
            <Summary result={job.result} />
          ) : (
            <Card className="results-card">
              <Space className="table-tools" wrap>
                <Input.Search
                  aria-label="Поиск по результатам"
                  placeholder="Артикул, категория или причина"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  allowClear
                  style={{ width: 320 }}
                />
                <Select
                  aria-label="Фильтр статуса"
                  placeholder="Все статусы"
                  value={status || undefined}
                  allowClear
                  onChange={(v) => setStatus(v || "")}
                  options={[
                    ...new Set(rows.map((r) => r.status).filter(Boolean)),
                  ].map((s) => ({ label: s, value: s }))}
                  style={{ width: 230 }}
                />
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => void loadRows()}
                >
                  Обновить
                </Button>
                <Text type="secondary">Найдено: {filtered.length}</Text>
              </Space>
              <Spin spinning={loading}>
                <ResultTable
                  rows={filtered}
                  schema={schema}
                  onSelect={select}
                />
              </Spin>
            </Card>
          )}
        </>
      )}
      {!job && (
        <Card>
          <Empty
            description={
              module === "tnved"
                ? "Выберите Excel для начала классификации"
                : "Загрузите три актуальных файла, чтобы начать анализ"
            }
          />
        </Card>
      )}
      <Details row={selected} onClose={() => setSelected(null)} />
    </>
  );
}

function HistoryPage({ open }: { open: (j: Job) => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    allRows<Job>("/api/history", 500)
      .then(setJobs)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <Title level={3}>История операций</Title>
      {error && <Alert type="error" title={error} />}
      <Table
        dataSource={jobs}
        rowKey="id"
        pagination={{ pageSize: 25 }}
        columns={[
          {
            title: "Дата",
            dataIndex: "created_at",
            render: (v) => new Date(v).toLocaleString("ru-RU"),
          },
          {
            title: "Модуль",
            dataIndex: "module",
            render: (v) =>
              v === "tnved" ? "Коды ТН ВЭД" : "Коммерческая аналитика",
          },
          { title: "Запуск", dataIndex: "title" },
          {
            title: "Исходные файлы",
            render: (_, r) => r.files.map((f) => f.name).join("; "),
          },
          {
            title: "Статус",
            dataIndex: "status",
            render: (v) => <Status value={v} />,
          },
          {
            title: "Действия",
            render: (_, r) => (
              <Space>
                <Button onClick={() => open(r)}>Открыть</Button>
                {r.status === "completed" && (
                  <Button
                    icon={<DownloadOutlined />}
                    href={`/api/${r.module}/runs/${r.id}/export`}
                  />
                )}
              </Space>
            ),
          },
        ]}
      />
    </>
  );
}

function SettingsPage() {
  const [settings, setSettings] = useState<DataRow | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<DataRow>("/api/settings")
      .then(setSettings)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <Title level={3}>Настройки</Title>
      {error && <Alert type="error" title={error} />}
      <Card title="Параметры локальной платформы">
        {settings ? (
          <Descriptions
            bordered
            column={1}
            items={[
              { key: "v", label: "Версия", children: settings.version },
              { key: "db", label: "Хранилище", children: settings.storage },
              {
                key: "size",
                label: "Максимальный размер файла",
                children: `${settings.max_upload_mb} МБ`,
              },
              {
                key: "jobs",
                label: "Одновременные задания",
                children: settings.workers,
              },
              {
                key: "alta",
                label: "Источник кодов",
                children: (
                  <a
                    href={settings.alta_source}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Alta.ru
                  </a>
                ),
              },
              {
                key: "resources",
                label: "Встроенные ресурсы",
                children: settings.resources.map((s: string) => (
                  <div key={s}>{s}</div>
                )),
              },
            ]}
          />
        ) : (
          <Spin />
        )}
      </Card>
      <Card title="Правила обработки">
        <p>
          Файлы результата сохраняются отдельно от исходников. Существующие коды
          ТН ВЭД сохраняются, пока не включена их проверка.
        </p>
        <p>
          Параметры подключения к БД и хранения задаются при запуске приложения.
          Бизнес-правила закреплены в приложенных регламентах.
        </p>
      </Card>
    </>
  );
}

export default function App() {
  const [page, setPage] = useState("home");
  const [ids, setIds] = useState<Record<string, string | null>>({
    merchandise: null,
    tnved: null,
  });
  function open(j: Job) {
    setIds((prev) => ({ ...prev, [j.module]: j.id }));
    setPage(j.module);
  }
  return (
    <Layout className="app-shell">
      <Layout.Sider width={230} theme="light" className="sidebar">
        <div className="brand">
          KANZLER<span>BUSINESS PLATFORM</span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[page]}
          onClick={(e) => setPage(e.key)}
          items={[
            { key: "home", icon: <AppstoreOutlined />, label: "Главная" },
            {
              key: "merchandise",
              icon: <BarChartOutlined />,
              label: "Коммерческая аналитика",
            },
            { key: "tnved", icon: <FileExcelOutlined />, label: "Коды ТН ВЭД" },
            { key: "history", icon: <HistoryOutlined />, label: "История" },
            { key: "settings", icon: <SettingOutlined />, label: "Настройки" },
          ]}
        />
        <div className="sidebar-footer">
          Внутренняя платформа
          <br />
          <span>Версия 0.1</span>
        </div>
      </Layout.Sider>
      <Layout>
        <Layout.Header className="topbar">
          <span>Рабочее пространство</span>
          <Text type="secondary">KANZLER · Коммерческие операции</Text>
        </Layout.Header>
        <Layout.Content className="content">
          {page === "home" && (
            <>
              <div className="page-title">
                <div>
                  <Title level={3}>Рабочее пространство</Title>
                  <Text type="secondary">
                    Аналитика коллекций и классификация номенклатуры
                  </Text>
                </div>
              </div>
              <div className="module-grid">
                <Card
                  title={
                    <>
                      <BarChartOutlined /> Коммерческая аналитика
                    </>
                  }
                >
                  <p>
                    Сопоставление поартикульного плана и фактических продаж.
                    Статусы, причины отклонений, вторая поставка и ценовые
                    решения.
                  </p>
                  <Button type="primary" onClick={() => setPage("merchandise")}>
                    Открыть аналитику
                  </Button>
                </Card>
                <Card
                  title={
                    <>
                      <FileExcelOutlined /> Коды ТН ВЭД
                    </>
                  }
                >
                  <p>
                    Классификация товаров по характеристикам с подтверждением
                    Alta.ru. Результат в исходном Excel с комментариями по
                    спорным позициям.
                  </p>
                  <Button type="primary" onClick={() => setPage("tnved")}>
                    Открыть классификацию
                  </Button>
                </Card>
              </div>
              <Card title="Возвращайтесь к ранее выполненным операциям">
                <p>
                  Исходные файлы, результаты, сообщения проверки и
                  сформированные Excel доступны в истории.
                </p>
                <Button onClick={() => setPage("history")}>
                  История операций
                </Button>
              </Card>
            </>
          )}
          {(page === "merchandise" || page === "tnved") && (
            <ModulePage
              key={page}
              module={page}
              jobId={ids[page]}
              onCreated={(id) => setIds((prev) => ({ ...prev, [page]: id }))}
            />
          )}
          {page === "history" && <HistoryPage open={open} />}
          {page === "settings" && <SettingsPage />}
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
