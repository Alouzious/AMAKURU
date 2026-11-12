import { render } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { Lang, t } from "./messages";

type Topic = { id: string; label: string; prompt: string };
type Source = {
  office_name?: string | null;
  last_verified?: string | null;
};
type Handoff = {
  title?: string;
  office_name?: string | null;
  phone?: string | null;
  email?: string | null;
  opening_hours?: string | null;
};
type Msg = {
  role: "user" | "bot";
  text: string;
  source?: Source | null;
  handoff?: Handoff | null;
  traceId?: string;
};

type Config = {
  apiBase: string;
  key: string;
  language?: Lang;
};

declare global {
  interface Window {
    AmakuruConfig?: Config;
    AmakuruWidget?: { mount: (el?: HTMLElement) => void };
  }
}

const STYLE = `
:host{all:initial}
*{box-sizing:border-box;font-family:Georgia,"Times New Roman",serif}
.wrap{position:fixed;right:16px;bottom:16px;z-index:2147483000;color:#1c1917}
.btn{border:0;border-radius:999px;padding:12px 18px;background:#0f766e;color:#fff;font:600 14px/1.2 system-ui,sans-serif;cursor:pointer;box-shadow:0 8px 24px rgba(15,23,42,.25)}
.panel{width:min(360px,calc(100vw - 24px));height:min(520px,70vh);background:#faf7f2;border:1px solid #d6d3d1;border-radius:16px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 50px rgba(28,25,23,.2)}
.head{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;background:#134e4a;color:#ecfdf5;font:600 14px system-ui,sans-serif}
.head button{background:transparent;border:0;color:#ecfdf5;cursor:pointer;font:14px system-ui,sans-serif}
.privacy{padding:8px 12px;font:12px/1.4 system-ui,sans-serif;color:#57534e;background:#f5f5f4}
.topics{display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px}
.chip{border:1px solid #a8a29e;background:#fff;border-radius:999px;padding:6px 10px;font:12px system-ui,sans-serif;cursor:pointer}
.msgs{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
.bubble{max-width:90%;padding:10px 12px;border-radius:12px;font:14px/1.45 Georgia,serif;white-space:pre-wrap}
.user{align-self:flex-end;background:#0f766e;color:#fff}
.bot{align-self:flex-start;background:#fff;border:1px solid #e7e5e4;color:#1c1917}
.meta{margin-top:6px;font:11px/1.3 system-ui,sans-serif;color:#78716c}
.hand{margin-top:8px;padding:8px;border:1px dashed #a8a29e;border-radius:8px;font:12px system-ui,sans-serif}
.foot{display:flex;gap:8px;padding:10px;border-top:1px solid #e7e5e4;background:#fff}
.foot input{flex:1;border:1px solid #d6d3d1;border-radius:10px;padding:10px;font:14px system-ui,sans-serif}
.foot button{border:0;border-radius:10px;background:#0f766e;color:#fff;padding:0 14px;font:600 13px system-ui,sans-serif;cursor:pointer}
.lang{display:flex;gap:4px;padding:0 12px 8px}
.lang button{border:1px solid #d6d3d1;background:#fff;border-radius:6px;padding:2px 6px;font:11px system-ui,sans-serif;cursor:pointer}
.lang .on{background:#134e4a;color:#fff;border-color:#134e4a}
.status{padding:0 12px 8px;font:12px system-ui,sans-serif;color:#b45309}
`;

function readConfig(): Config {
  const cfg = window.AmakuruConfig;
  if (!cfg?.apiBase || !cfg.key) {
    throw new Error("AmakuruConfig.apiBase and AmakuruConfig.key are required");
  }
  return { ...cfg, language: cfg.language || "en" };
}

function Widget() {
  const cfg = useMemo(() => readConfig(), []);
  const [open, setOpen] = useState(false);
  const [lang, setLang] = useState<Lang>((cfg.language as Lang) || "en");
  const [topics, setTopics] = useState<Topic[]>([]);
  const [welcome, setWelcome] = useState("");
  const [privacy, setPrivacy] = useState("");
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  useEffect(() => {
    if (!open) return;
    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${cfg.apiBase}/api/v1/public/chat/bootstrap`, {
          headers: { "X-Amakuru-Key": cfg.key },
          signal: ctrl.signal,
        });
        if (!res.ok) throw new Error("bootstrap failed");
        const data = await res.json();
        setTopics(data.quick_topics || []);
        setWelcome(data.welcome_message || t(lang, "welcome"));
        setPrivacy(data.privacy_notice || t(lang, "privacy"));
      } catch {
        setStatus(t(lang, "offline"));
      }
    })();
    return () => ctrl.abort();
  }, [open, cfg.apiBase, cfg.key, lang]);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    if (!navigator.onLine) {
      setStatus(t(lang, "offline"));
      return;
    }
    setBusy(true);
    setStatus("");
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setInput("");
    const botIndexHint = { i: -1 };
    setMsgs((m) => {
      botIndexHint.i = m.length;
      return [...m, { role: "bot", text: "" }];
    });
    const slow = window.setTimeout(() => setStatus(t(lang, "slow")), 2500);
    try {
      const res = await fetch(`${cfg.apiBase}/api/v1/public/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Amakuru-Key": cfg.key,
        },
        body: JSON.stringify({
          question,
          language: lang,
          conversation_id: convId,
        }),
      });
      if (!res.ok || !res.body) throw new Error("stream failed");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let meta: { conversation_id?: string; trace_id?: string; source?: Source; handoff?: Handoff } =
        {};
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const lines = part.split("\n");
          let event = "message";
          let data = "";
          for (const line of lines) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            if (line.startsWith("data:")) data += line.slice(5).trim();
          }
          if (!data) continue;
          const payload = JSON.parse(data);
          if (event === "meta") {
            meta = payload;
            if (payload.conversation_id) setConvId(payload.conversation_id);
          } else if (event === "token") {
            setMsgs((m) => {
              const copy = [...m];
              const last = copy[copy.length - 1];
              if (last?.role === "bot") {
                copy[copy.length - 1] = { ...last, text: last.text + (payload.text || "") };
              }
              return copy;
            });
          } else if (event === "done") {
            setMsgs((m) => {
              const copy = [...m];
              const last = copy[copy.length - 1];
              if (last?.role === "bot") {
                copy[copy.length - 1] = {
                  ...last,
                  text: payload.reply || last.text,
                  source: meta.source,
                  handoff: meta.handoff,
                  traceId: meta.trace_id,
                };
              }
              return copy;
            });
          }
        }
      }
    } catch {
      setStatus(t(lang, "offline"));
      setMsgs((m) => m.filter((x, idx) => !(idx === m.length - 1 && x.role === "bot" && !x.text)));
    } finally {
      window.clearTimeout(slow);
      setBusy(false);
      setStatus("");
    }
  }

  async function feedback(traceId: string, rating: number) {
    await fetch(`${cfg.apiBase}/api/v1/public/chat/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Amakuru-Key": cfg.key,
      },
      body: JSON.stringify({ trace_id: traceId, conversation_id: convId, rating }),
    }).catch(() => undefined);
  }

  return (
    <div class="wrap">
      {!open ? (
        <button class="btn" type="button" onClick={() => setOpen(true)}>
          {t(lang, "open")}
        </button>
      ) : (
        <div class="panel" role="dialog" aria-label="Amakuru chat">
          <div class="head">
            <span>Amakuru</span>
            <button type="button" onClick={() => setOpen(false)}>
              {t(lang, "close")}
            </button>
          </div>
          <div class="privacy">{privacy || t(lang, "privacy")}</div>
          <div class="lang">
            {(["en", "lg", "nyn", "sw"] as Lang[]).map((code) => (
              <button
                key={code}
                type="button"
                class={lang === code ? "on" : ""}
                onClick={() => setLang(code)}
              >
                {code}
              </button>
            ))}
          </div>
          {msgs.length === 0 && (
            <>
              <div class="privacy">{welcome || t(lang, "welcome")}</div>
              <div class="topics">
                {topics.map((topic) => (
                  <button
                    key={topic.id}
                    class="chip"
                    type="button"
                    onClick={() => ask(topic.prompt)}
                  >
                    {topic.label}
                  </button>
                ))}
              </div>
            </>
          )}
          {status && <div class="status">{status}</div>}
          <div class="msgs">
            {msgs.map((m, i) => (
              <div key={i} class={`bubble ${m.role === "user" ? "user" : "bot"}`}>
                {m.text}
                {m.source?.office_name && (
                  <div class="meta">
                    {t(lang, "source")}: {m.source.office_name}
                    {m.source.last_verified ? ` · ${m.source.last_verified}` : ""}
                  </div>
                )}
                {m.handoff && (
                  <div class="hand">
                    <strong>{m.handoff.title || t(lang, "talking")}</strong>
                    <div>{m.handoff.office_name}</div>
                    <div>{m.handoff.phone}</div>
                    <div>{m.handoff.email}</div>
                    <div>{m.handoff.opening_hours}</div>
                  </div>
                )}
                {m.traceId && m.role === "bot" && (
                  <div class="meta">
                    <button type="button" class="chip" onClick={() => feedback(m.traceId!, 1)}>
                      {t(lang, "thumbsUp")}
                    </button>{" "}
                    <button type="button" class="chip" onClick={() => feedback(m.traceId!, -1)}>
                      {t(lang, "thumbsDown")}
                    </button>
                  </div>
                )}
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <form
            class="foot"
            onSubmit={(e) => {
              e.preventDefault();
              ask(input);
            }}
          >
            <input
              value={input}
              onInput={(e) => setInput((e.target as HTMLInputElement).value)}
              placeholder={t(lang, "placeholder")}
              aria-label={t(lang, "placeholder")}
              disabled={busy}
            />
            <button type="submit" disabled={busy}>
              {t(lang, "send")}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

function mount(target?: HTMLElement) {
  const host = target || document.createElement("div");
  if (!target) {
    host.id = "amakuru-widget-host";
    document.body.appendChild(host);
  }
  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = STYLE;
  const root = document.createElement("div");
  shadow.append(style, root);
  render(<Widget />, root);
}

window.AmakuruWidget = { mount };
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => mount());
} else {
  mount();
}
