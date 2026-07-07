import React, { useState, useCallback } from "react";
import InputPanel from "./components/InputPanel";
import PreviewPanel from "./components/PreviewPanel";
import ResultPanel from "./components/ResultPanel";
import ProgressBar from "./components/ProgressBar";

interface WorkflowStep {
  action: string;
  target: string;
  params: Record<string, any>;
  reason: string;
}

interface IntentResult {
  success: boolean;
  understood: string;
  workflow?: { steps: WorkflowStep[] };
  error?: string;
}

export default function App() {
  const [intent, setIntent] = useState<IntentResult | null>(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(async (input: string) => {
    setLoading(true);
    setStatus("正在理解你的需求...");
    setProgress(0.1);

    try {
      // @ts-ignore
      const result = await window.memento.submitIntent(input, null);
      setIntent(result);

      if (result.success && result.workflow) {
        setStatus(`AI 理解: ${result.understood}`);
        setProgress(0.3);

        // 执行工作流
        setStatus("正在执行工作流...");
        // @ts-ignore
        const execResult = await window.memento.executeWorkflow(result.workflow);
        setProgress(1.0);
        setStatus(execResult.success ? "完成!" : "执行失败");
        setOutputPath(execResult.output || "");
      } else {
        setStatus(`理解失败: ${result.error}`);
        setProgress(0);
      }
    } catch (err: any) {
      setStatus(`错误: ${err.message}`);
      setProgress(0);
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>Memento-X</h1>
        <span style={styles.subtitle}>AI 视频编辑 — 说出你的创意</span>
      </header>

      <main style={styles.main}>
        <InputPanel onSubmit={handleSubmit} disabled={loading} />

        {loading && <ProgressBar progress={progress} status={status} />}

        {intent && intent.workflow && (
          <PreviewPanel
            understood={intent.understood}
            steps={intent.workflow.steps}
          />
        )}

        {outputPath && <ResultPanel path={outputPath} />}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: "100vh",
    background: "#0a0a0f",
    color: "#e0e0e0",
    fontFamily: "system-ui, sans-serif",
  },
  header: {
    padding: "24px 32px",
    borderBottom: "1px solid #1a1a2e",
    display: "flex",
    alignItems: "baseline",
    gap: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: 700,
    margin: 0,
    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
  },
  subtitle: {
    fontSize: 14,
    color: "#666",
  },
  main: {
    maxWidth: 900,
    margin: "0 auto",
    padding: "32px 24px",
  },
};