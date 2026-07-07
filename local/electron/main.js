const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let mainWindow;
let schedulerProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: "Memento-X",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 开发模式加载 Vite dev server，生产模式加载打包文件
  const isDev = process.env.NODE_ENV !== "production";
  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, "ui", "dist", "index.html"));
  }
}

// ── IPC 通信：UI ↔ 调度器 ──

ipcMain.handle("intent:submit", async (event, { input, context }) => {
  // 发送意图理解请求到云端，获取工作流
  const response = await fetch("http://localhost:8000/api/v1/intent/understand", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input, context }),
  });

  if (!response.ok) {
    throw new Error(`云端请求失败: ${response.status}`);
  }

  return await response.json();
});

ipcMain.handle("workflow:execute", async (event, workflow) => {
  // 启动 Python 调度器执行工作流
  return new Promise((resolve, reject) => {
    schedulerProcess = spawn("python", [
      "-m", "local.scheduler.executor",
      "--workflow", JSON.stringify(workflow),
    ]);

    let output = "";
    schedulerProcess.stdout.on("data", (data) => {
      output += data.toString();
      // 发送进度更新到 UI
      mainWindow?.webContents.send("workflow:progress", data.toString());
    });

    schedulerProcess.stderr.on("data", (data) => {
      mainWindow?.webContents.send("workflow:error", data.toString());
    });

    schedulerProcess.on("close", (code) => {
      resolve({ success: code === 0, output });
    });

    schedulerProcess.on("error", (err) => {
      reject(err);
    });
  });
});

ipcMain.handle("hardware:detect", async () => {
  // 调用 Python 硬件检测
  return new Promise((resolve, reject) => {
    const proc = spawn("python", ["-m", "local.launcher.detector"]);
    let output = "";
    proc.stdout.on("data", (data) => { output += data.toString(); });
    proc.on("close", () => resolve(output));
    proc.on("error", reject);
  });
});

// ── 应用生命周期 ──

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (schedulerProcess) schedulerProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});