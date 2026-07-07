import React from "react";

interface Props {
  progress: number;
  status: string;
}

export default function ProgressBar({ progress, status }: Props) {
  return (
    <div style={styles.container}>
      <div style={styles.track}>
        <div
          style={{
            ...styles.fill,
            width: `${Math.round(progress * 100)}%`,
          }}
        />
      </div>
      <p style={styles.status}>{status}</p>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    marginTop: 20,
  },
  track: {
    height: 6,
    background: "#1e1e3a",
    borderRadius: 3,
    overflow: "hidden",
  },
  fill: {
    height: "100%",
    background: "linear-gradient(90deg, #6366f1, #8b5cf6)",
    borderRadius: 3,
    transition: "width 0.3s ease",
  },
  status: {
    marginTop: 8,
    fontSize: 13,
    color: "#888",
  },
};