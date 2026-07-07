import React from "react";

interface Step {
  action: string;
  target: string;
  params: Record<string, any>;
  reason: string;
}

interface Props {
  understood: string;
  steps: Step[];
}

const ACTION_LABELS: Record<string, string> = {
  matting: "抠图",
  tracking: "追踪",
  replace: "替换",
  composite: "合成",
  color_grade: "调色",
  subtitle: "字幕",
  effect: "特效",
  crop: "裁剪",
  stabilize: "防抖",
  denoise: "降噪",
};

export default function PreviewPanel({ understood, steps }: Props) {
  return (
    <div style={styles.container}>
      <h3 style={styles.heading}>AI 理解</h3>
      <p style={styles.understood}>{understood}</p>

      <h3 style={styles.heading}>工作流步骤</h3>
      <div style={styles.steps}>
        {steps.map((step, i) => (
          <div key={i} style={styles.step}>
            <span style={styles.stepIndex}>{i + 1}</span>
            <div>
              <strong>{ACTION_LABELS[step.action] || step.action}</strong>
              {step.target && <span style={styles.target}> → {step.target}</span>}
              <p style={styles.reason}>{step.reason}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    marginTop: 24,
    padding: 24,
    background: "#12121f",
    borderRadius: 12,
    border: "1px solid #1e1e3a",
  },
  heading: {
    fontSize: 14,
    fontWeight: 600,
    color: "#888",
    marginBottom: 8,
    textTransform: "uppercase" as const,
    letterSpacing: 1,
  },
  understood: {
    color: "#a78bfa",
    marginBottom: 20,
    fontSize: 15,
  },
  steps: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 12,
  },
  step: {
    display: "flex",
    gap: 12,
    alignItems: "flex-start",
    padding: "12px 16px",
    background: "#0a0a1a",
    borderRadius: 8,
  },
  stepIndex: {
    width: 28,
    height: 28,
    borderRadius: 14,
    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 13,
    fontWeight: 700,
    flexShrink: 0,
  },
  target: {
    color: "#6366f1",
    fontSize: 13,
  },
  reason: {
    margin: "4px 0 0",
    fontSize: 12,
    color: "#555",
  },
};