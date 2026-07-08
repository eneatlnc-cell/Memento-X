const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let mainWindow;
let tray = null;
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

  const isDev = process.env.NODE_ENV !== "production";
  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, "ui", "dist", "index.html"));
  }

  // 关闭窗口时隐藏到托盘而不是退出
  mainWindow.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  // 创建系统托盘图标（16x16 占位图标）
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip("Memento-X");

  const contextMenu = Menu.buildFromTemplate([
    { label: "显示窗口", click: () => mainWindow?.show() },
    { type: "separator" },
    {
      label: "开机自启",
      type: "checkbox",
      checked: app.getLoginItemSettings().openAtLogin,
      click: (menuItem) => {
        app.setLoginItemSettings({ openAtLogin: menuItem.checked });
      },
    },
    { type: "separator" },
    {
      label: "退出",
      click: () => {
        app.isQuitting = true;
        if (schedulerProcess) schedulerProcess.kill();
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => mainWindow?.show());
}

// ── IPC 通信 ──

ipcMain.handle("intent:submit", async (event, { input, context }) => {
  const response = await fetch("http://localhost:8000/api/v1/intent/understand", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input, context }),
  });
  if (!response.ok) throw new Error(`云端请求失败: ${response.status}`);
  return await response.json();
});

ipcMain.handle("workflow:execute", async (event, workflow) => {
  return new Promise((resolve, reject) => {
    schedulerProcess = spawn("python", [
      "-m", "local.scheduler.executor",
      "--workflow", JSON.stringify(workflow),
    ]);
    let output = "";
    schedulerProcess.stdout.on("data", (data) => {
      output += data.toString();
      mainWindow?.webContents.send("workflow:progress", data.toString());
    });
    schedulerProcess.stderr.on("data", (data) => {
      mainWindow?.webContents.send("workflow:error", data.toString());
    });
    schedulerProcess.on("close", (code) => {
      resolve({ success: code === 0, output });
    });
    schedulerProcess.on("error", reject);
  });
});

ipcMain.handle("hardware:detect", async () => {
  return new Promise((resolve, reject) => {
    const proc = spawn("python", ["-m", "local.launcher.detector"]);
    let output = "";
    proc.stdout.on("data", (data) => { output += data.toString(); });
    proc.on("close", () => resolve(output));
    proc.on("error", reject);
  });
});

// ── 应用生命周期 ──

app.whenReady().then(() => {
  createWindow();
  createTray();

  // 开机自启
  app.setLoginItemSettings({ openAtLogin: true });
});

app.on("before-quit", () => {
  app.isQuitting = true;
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
  else mainWindow?.show();
});