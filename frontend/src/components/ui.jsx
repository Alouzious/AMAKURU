import { useState } from "react";

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="font-display text-2xl text-[var(--ink)] md:text-[1.75rem]">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">{subtitle}</p>}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function Stat({ label, value }) {
  return (
    <div className="ui-panel p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
        {label}
      </p>
      <p className="mt-2 font-display text-2xl text-accent">{value}</p>
    </div>
  );
}

export function Panel({ children, className = "" }) {
  return <section className={`ui-panel p-4 md:p-5 ${className}`}>{children}</section>;
}

export function Empty({ children }) {
  return <p className="py-10 text-center text-sm text-[var(--muted)]">{children}</p>;
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
  className = "",
}) {
  const base = variant === "primary" ? "ui-btn-primary" : "ui-btn-ghost";
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${className}`}>
      {children}
    </button>
  );
}

export function CopyButton({ text, label = "Copy", copiedLabel = "Copied" }) {
  const [copied, setCopied] = useState(false);
  async function onCopy() {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }
  return (
    <Button variant="ghost" onClick={onCopy} disabled={!text}>
      {copied ? copiedLabel : label}
    </Button>
  );
}

export function CodeBlock({ children }) {
  return (
    <pre className="mt-2 overflow-x-auto rounded-lg bg-[#0b1220] p-3 font-mono text-[12px] leading-relaxed text-[#e8eef6]">
      {children}
    </pre>
  );
}
