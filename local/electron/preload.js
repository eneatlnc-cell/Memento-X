const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("memento", {
  // 意图理解
  submitIntent: (input, context) =>
    ipcRenderer.invoke("intent:submit", { input, context }),

  // 工作流执行
  executeWorkflow: (workflow) =>
    ipcRenderer.invoke("workflow:execute", workflow),

  // 硬件检测
  detectHardware: () =>
    ipcRenderer.invoke("hardware:detect"),

  // 事件监听
  onWorkflowProgress: (callback) => {
    ipcRenderer.on("workflow:progress", (_, data) => callback(data));
  },
  onWorkflowError: (callback) => {
    ipcRenderer.on("workflow:error", (_, data) => callback(data));
  },
});