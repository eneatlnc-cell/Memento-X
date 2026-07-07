import React, { useState } from "react";

interface Props {
  onSubmit: (input: string) => void;
  disabled: boolean;
}

export default function InputPanel({ onSubmit, disabled }: Props) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSubmit(input.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="描述你想对视频做什么...&#10;例如：把这个人换成钢铁侠，背景改成火星"
        style={styles.textarea}
        rows={4}
        disabled={disabled}
      />
      <button
        type="submit"
        disabled={disabled || !input.trim()}
        style={{
          ...styles.button,
          opacity: disabled || !input.trim() ? 0.5 : 1,
        }}
      >
        {disabled ? "处理中..." : "生成"}
      </button>
    </form>
  );
}

const styles: Record<string, React.CSSProperties> = {
  form: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  textarea: {
    width: "100%",
    padding: "16px",
    background: "#12121f",
    border: "1px solid #1e1e3a",
    borderRadius: 12,
    color: "#e0e0e0",
    fontSize: 16,
    resize: "vertical",
    outline: "none",
    fontFamily: "inherit",
  },
  button: {
    alignSelf: "flex-end",
    padding: "12px 32px",
    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
    border: "none",
    borderRadius: 10,
    color: "white",
    fontSize: 16,
    fontWeight: 600,
    cursor: "pointer",
    transition: "opacity 0.2s",
  },
};