import React from "react";

interface Props {
  path: string;
}

export default function ResultPanel({ path }: Props) {
  return (
    <div style={styles.container}>
      <h3 style={styles.heading}>成片</h3>
      <video
        src={`file://${path}`}
        controls
        style={styles.video}
        autoPlay
        loop
      />
      <p style={styles.path}>{path}</p>
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
    marginBottom: 12,
    textTransform: "uppercase" as const,
    letterSpacing: 1,
  },
  video: {
    width: "100%",
    borderRadius: 8,
    maxHeight: 500,
  },
  path: {
    marginTop: 8,
    fontSize: 12,
    color: "#555",
    wordBreak: "break-all" as const,
  },
};