import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, App as AntApp } from "antd";
import ruRU from "antd/locale/ru_RU";
import App from "./App";
import "./style.css";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={ruRU}
      componentSize="small"
      theme={{
        token: {
          colorPrimary: "#284a69",
          borderRadius: 3,
          fontFamily: "Segoe UI, Arial, sans-serif",
          fontSize: 13,
          colorBgLayout: "#f3f5f7",
        },
        components: { Table: { cellPaddingBlockSM: 7, headerBg: "#f0f3f6" } },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
