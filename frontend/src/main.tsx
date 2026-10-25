import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
} from "pdfjs-dist";
import worker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Download,
  FileText,
  FolderOpen,
  Languages,
  LoaderCircle,
  LockKeyhole,
  Minus,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import "./style.css";

GlobalWorkerOptions.workerSrc = worker;
const API = "/api/v1";
let token = "";
type Block = {
  id: string;
  source: string;
  target: string | null;
  bbox_pdf_pt: number[];
  reading_order: number;
  role: string;
  protection_mode: string;
  warnings: string[];
  source_confidence: number;
  segmentation_confidence: number;
  override_reason: string | null;
};
type Page = {
  page_index: number;
  width_pt: number;
  height_pt: number;
  classification: string;
  blocks: Block[];
  warnings: string[];
};
type IR = { pages: Page[]; document: { filename: string; page_count: number } };
type Job = {
  id: string;
  filename: string;
  status: string;
  message: string;
  progress: number;
  output_available: boolean;
  updated_at: number;
};
type CheckItem = { name: string; ready: boolean; detail: string; fix: string };
type Diagnostic = {
  severity: string;
  check: string;
  message: string;
  page: number | null;
  block_id: string | null;
};
const busyStates = [
  "queued",
  "analyze",
  "ocr",
  "translate",
  "sanitize",
  "compile",
  "qa",
];
async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(API + path, {
    ...options,
    headers: { "X-Kizuna-Token": token, ...options.headers },
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail),
    );
  }
  return res.json();
}
function Preview({
  url,
  page,
  zoom,
  regions,
  selected,
  onSelect,
  label,
  onScroll,
  scrollRef,
}: {
  url?: string;
  page: number;
  zoom: number;
  regions: Page | undefined;
  selected: string;
  onSelect: (b: Block) => void;
  label: string;
  onScroll: (e: React.UIEvent<HTMLDivElement>) => void;
  scrollRef: React.RefObject<HTMLDivElement | null>;
}) {
  const canvas = useRef<HTMLCanvasElement>(null),
    [doc, setDoc] = useState<PDFDocumentProxy | null>(null),
    [error, setError] = useState(""),
    [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    setDoc(null);
    setError("");
    if (!url) return;
    const task = getDocument({
      url,
      cMapUrl: "/pdfjs/cmaps/",
      cMapPacked: true,
      standardFontDataUrl: "/pdfjs/standard_fonts/",
      wasmUrl: "/pdfjs/wasm/",
    });
    task.promise.then(setDoc).catch((e) => setError(e.message));
    return () => {
      void task.destroy();
    };
  }, [url]);
  useEffect(() => {
    if (!doc || !canvas.current) return;
    let cancelled = false;
    let renderTask: { cancel: () => void } | undefined;
    void doc.getPage(page + 1).then((p) => {
      if (cancelled || !canvas.current) return;
      const viewport = p.getViewport({ scale: zoom });
      const c = canvas.current;
      const ratio = window.devicePixelRatio || 1;
      c.width = viewport.width * ratio;
      c.height = viewport.height * ratio;
      setSize({ width: viewport.width, height: viewport.height });
      const task = p.render({
        canvas: c,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      renderTask = task;
      void task.promise.catch((e) => {
        if (e.name !== "RenderingCancelledException") setError(e.message);
      });
    });
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [doc, page, zoom]);
  return (
    <section className="preview">
      <div className="preview-label">
        <span className="language-tag">
          {label === "Original" ? "JA" : "EN"}
        </span>
        {label}
        <span className="preview-note">
          {label === "Original" ? "Source document" : "XeLaTeX reconstruction"}
        </span>
      </div>
      <div className="paper-scroll" ref={scrollRef} onScroll={onScroll}>
        {!url ? (
          <div className="preview-empty">
            <Languages size={34} />
            <h3>Your English edition</h3>
            <p>
              Translate a document to compare its layout
              <br />
              and review each region here.
            </p>
          </div>
        ) : error ? (
          <p className="error">{error}</p>
        ) : (
          <div className="paper" style={size.width ? size : undefined}>
            <canvas ref={canvas} style={size.width ? size : undefined} />
            {doc &&
              regions?.blocks.map((b) => (
                <button
                  key={b.id}
                  aria-label={`Select region: ${b.source.slice(0, 40)}`}
                  title={b.source}
                  className={`region ${selected === b.id ? "selected" : ""}`}
                  style={{
                    left: b.bbox_pdf_pt[0] * zoom,
                    top: b.bbox_pdf_pt[1] * zoom,
                    width: (b.bbox_pdf_pt[2] - b.bbox_pdf_pt[0]) * zoom,
                    height: (b.bbox_pdf_pt[3] - b.bbox_pdf_pt[1]) * zoom,
                  }}
                  onClick={() => onSelect(b)}
                />
              ))}
          </div>
        )}
      </div>
    </section>
  );
}
function App() {
  const [job, setJob] = useState<Job | null>(null),
    [ir, setIR] = useState<IR | null>(null),
    [recent, setRecent] = useState<Job[]>([]),
    [checks, setChecks] = useState<CheckItem[]>([]),
    [modelReady, setModelReady] = useState(false),
    [setup, setSetup] = useState(false),
    [accepted, setAccepted] = useState(false),
    [downloading, setDownloading] = useState(false),
    [downloadBytes, setDownloadBytes] = useState(0),
    [error, setError] = useState(""),
    [working, setWorking] = useState(false),
    [scan, setScan] = useState(false),
    [password, setPassword] = useState(""),
    [drag, setDrag] = useState(false),
    [page, setPage] = useState(0),
    [zoom, setZoom] = useState(0.85),
    [selected, setSelected] = useState(""),
    [draft, setDraft] = useState(""),
    [mode, setMode] = useState("translate"),
    [reason, setReason] = useState(""),
    [order, setOrder] = useState(0),
    [qa, setQA] = useState<Diagnostic[]>([]),
    [tab, setTab] = useState("regions");
  const fileInput = useRef<HTMLInputElement>(null),
    leftScroll = useRef<HTMLDivElement>(null),
    rightScroll = useRef<HTMLDivElement>(null),
    sync = useRef(false);
  const busy = !!job && busyStates.includes(job.status),
    block = ir?.pages.flatMap((p) => p.blocks).find((b) => b.id === selected);
  async function run(action: () => Promise<void>) {
    setError("");
    setWorking(true);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function refreshChecks() {
    const d = await api<{ checks: CheckItem[]; model: { ready: boolean } }>(
      "/doctor",
    );
    setChecks(d.checks);
    setModelReady(d.model.ready);
  }
  async function loadJob(id: string) {
    const [j, d] = await Promise.all([
      api<Job>(`/jobs/${id}`),
      api<IR>(`/documents/${id}`),
    ]);
    setJob(j);
    setIR(d);
    setPage(0);
    setSelected("");
    setQA([]);
    localStorage.setItem("kizuna-last-job", id);
    if (["completed", "needs_review", "failed"].includes(j.status)) {
      try {
        const q = await api<{ diagnostics: Diagnostic[] }>(
          `/jobs/${id}/export/qa`,
        );
        setQA(q.diagnostics);
      } catch {}
    }
  }
  useEffect(() => {
    void run(async () => {
      const h = await api<{ session_token: string }>("/health");
      token = h.session_token;
      await refreshChecks();
      const jobs = await api<Job[]>("/jobs");
      setRecent(jobs);
      const saved = localStorage.getItem("kizuna-last-job");
      if (saved && jobs.some((j) => j.id === saved)) await loadJob(saved);
    });
  }, []);
  useEffect(() => {
    if (!busy || !job) return;
    const timer = setInterval(() => {
      void api<Job>(`/jobs/${job.id}`)
        .then(async (j) => {
          setJob(j);
          if (!busyStates.includes(j.status)) {
            setIR(await api<IR>(`/documents/${j.id}`));
            setRecent(await api<Job[]>("/jobs"));
            try {
              const q = await api<{ diagnostics: Diagnostic[] }>(
                `/jobs/${j.id}/export/qa`,
              );
              setQA(q.diagnostics);
            } catch {}
          }
        })
        .catch((e) => setError(e.message));
    }, 1000);
    return () => clearInterval(timer);
  }, [busy, job?.id]);
  useEffect(() => {
    if (!downloading) return;
    const timer = setInterval(() => {
      void api<{
        ready: boolean;
        status: string;
        bytes_on_disk: number;
        error: string | null;
      }>("/models/status").then((s) => {
        setDownloadBytes(s.bytes_on_disk);
        if (s.ready || s.status === "failed") {
          setDownloading(false);
          setModelReady(s.ready);
          if (s.error) setError(s.error);
          void refreshChecks();
        }
      });
    }, 2000);
    return () => clearInterval(timer);
  }, [downloading]);
  function select(b: Block) {
    setSelected(b.id);
    setDraft(b.target || "");
    setMode(b.protection_mode);
    setReason(b.override_reason || "");
    setOrder(b.reading_order);
    setTab("regions");
  }
  async function upload(file: File) {
    await run(async () => {
      if (file.size > 50 * 1024 * 1024)
        throw new Error("Please choose a PDF smaller than 50 MB.");
      const form = new FormData();
      form.append("file", file);
      form.append("allow_scans", String(scan));
      if (password) form.append("password", password);
      const j = await api<Job>("/documents", { method: "POST", body: form });
      setPassword("");
      await loadJob(j.id);
      setRecent(await api<Job[]>("/jobs"));
    });
  }
  function linkedScroll(
    e: React.UIEvent<HTMLDivElement>,
    other: HTMLDivElement | null,
  ) {
    if (sync.current || !other) return;
    sync.current = true;
    other.scrollTop = e.currentTarget.scrollTop;
    other.scrollLeft = e.currentTarget.scrollLeft;
    requestAnimationFrame(() => {
      sync.current = false;
    });
  }
  async function start(action: string) {
    if (!job) return;
    await run(async () => {
      setQA([]);
      setJob(await api<Job>(`/jobs/${job.id}/${action}`, { method: "POST" }));
    });
  }
  return (
    <>
      <header className="app-header">
        <a className="brand" href="/" aria-label="KizunaPDF home">
          <span className="brand-mark">絆</span>
          <span>
            Kizuna<span className="brand-light">PDF</span>
            <small>LOCAL TRANSLATION STUDIO</small>
          </span>
        </a>
        <div className="header-right">
          <span className="privacy">
            <LockKeyhole size={14} />
            100% on-device after model setup
          </span>
          <button className="model-pill" onClick={() => setSetup(true)}>
            <i className={modelReady ? "dot ready" : "dot"} />
            {modelReady ? "TranslateGemma ready" : "Model setup"}
            <Settings2 size={14} />
          </button>
        </div>
      </header>
      <main>
        <aside className="sidebar">
          <div className="section-eyebrow">WORKSPACE</div>
          <button
            className="new-document"
            onClick={() => fileInput.current?.click()}
            disabled={working}
          >
            <Plus size={17} />
            New document
          </button>
          <div className="sidebar-title">
            Recent documents <span>{recent.length}</span>
          </div>
          <nav>
            {recent.map((j) => (
              <button
                className={`document-item ${j.id === job?.id ? "active" : ""}`}
                key={j.id}
                onClick={() => void run(() => loadJob(j.id))}
              >
                <FileText size={17} />
                <span>
                  <strong>{j.filename}</strong>
                  <small>{j.status.replaceAll("_", " ")}</small>
                </span>
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <ShieldCheck size={20} />
            <strong>Your documents stay here.</strong>
            <p>
              Local models. Local processing.
              <br />
              No uploads to a cloud service.
            </p>
            <button className="text-button" onClick={() => setSetup(true)}>
              Environment checks <ArrowUpRight size={13} />
            </button>
          </div>
        </aside>
        <div className="workspace">
          <div className="workspace-heading">
            <div>
              <div className="section-eyebrow">
                JAPANESE <ArrowRight size={12} /> ENGLISH
              </div>
              <h1>
                {job ? job.filename : "A new language. The same document."}
              </h1>
              <p>
                {job
                  ? `${ir?.document.page_count || 0} pages · Editable LaTeX · Private workspace`
                  : "Translate Japanese PDFs on your Mac, with their layout in view."}
              </p>
            </div>
            {job && (
              <button
                className="secondary"
                onClick={() => {
                  setJob(null);
                  setIR(null);
                  setSelected("");
                }}
              >
                <FolderOpen size={16} />
                Change document
              </button>
            )}
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <CircleAlert size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          <input
            type="file"
            ref={fileInput}
            accept="application/pdf,.pdf"
            hidden
            onChange={(e) => {
              if (e.target.files?.[0]) void upload(e.target.files[0]);
              e.target.value = "";
            }}
          />
          {!job ? (
            <>
              <div
                className={`dropzone ${drag ? "drag" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDrag(true);
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDrag(false);
                  if (e.dataTransfer.files[0])
                    void upload(e.dataTransfer.files[0]);
                }}
              >
                <div className="upload-icon">
                  <FileText size={33} />
                  <span>JA</span>
                </div>
                <h2>Bring your document across.</h2>
                <p>
                  Drop a Japanese PDF here, or choose a file to begin.
                  <br />
                  Your original stays untouched.
                </p>
                <button
                  className="primary"
                  disabled={working}
                  onClick={() => fileInput.current?.click()}
                >
                  {working ? (
                    <LoaderCircle className="spin" size={17} />
                  ) : (
                    <Upload size={17} />
                  )}
                  Choose a PDF
                </button>
                <small>PDF only · Up to 50 MB · Up to 100 pages</small>
              </div>
              <div className="upload-options">
                <label>
                  <input
                    type="checkbox"
                    checked={scan}
                    onChange={(e) => setScan(e.target.checked)}
                  />{" "}
                  Enable experimental scanned PDF support
                </label>
                <input
                  aria-label="PDF password, if needed"
                  type="password"
                  placeholder="PDF password, if needed"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="intro-cards">
                <article>
                  <span>01</span>
                  <h3>Preserve the page</h3>
                  <p>
                    Keep vector artwork and page geometry, with explicit checks
                    for layout changes.
                  </p>
                </article>
                <article>
                  <span>02</span>
                  <h3>Review every region</h3>
                  <p>
                    Compare the source and translation. Correct text before
                    rebuilding.
                  </p>
                </article>
                <article>
                  <span>03</span>
                  <h3>Keep the source files</h3>
                  <p>
                    Export selectable English, editable LaTeX, and a detailed
                    quality report.
                  </p>
                </article>
              </div>
            </>
          ) : (
            <>
              <div className="job-bar">
                <div
                  className={`status-label ${job.status === "completed" ? "good" : ""}`}
                >
                  <span className={busy ? "spin" : ""}>
                    {busy ? (
                      <LoaderCircle size={16} />
                    ) : job.status === "completed" ? (
                      <Check size={16} />
                    ) : (
                      <CircleAlert size={16} />
                    )}
                  </span>
                  <div>
                    <strong>
                      {job.status === "completed"
                        ? "Quality checks passed"
                        : job.status.replaceAll("_", " ")}
                    </strong>
                    <small>{job.message}</small>
                  </div>
                </div>
                <div className="job-actions">
                  {busy ? (
                    <button
                      className="secondary"
                      onClick={() => void start("cancel")}
                    >
                      Stop
                    </button>
                  ) : (
                    <>
                      <button
                        className="secondary"
                        onClick={() => void start("rebuild")}
                        disabled={working}
                      >
                        {" "}
                        <RefreshCw size={15} />
                        Rebuild document
                      </button>
                      <button
                        className="primary"
                        onClick={() => void start("translate")}
                        disabled={working || !modelReady}
                      >
                        <Languages size={16} />
                        {job.status === "ready"
                          ? "Translate locally"
                          : "Resume translation"}
                      </button>
                    </>
                  )}
                </div>
                {busy && (
                  <div className="progress-track">
                    <i
                      style={{ width: `${Math.max(3, job.progress * 100)}%` }}
                    />
                  </div>
                )}
              </div>
              <div className="viewer-toolbar">
                <div>
                  <button
                    aria-label="Previous page"
                    disabled={page === 0}
                    onClick={() => setPage(page - 1)}
                  >
                    <ChevronLeft size={17} />
                  </button>
                  <span>
                    Page <strong>{page + 1}</strong> of {ir?.pages.length}
                  </span>
                  <button
                    aria-label="Next page"
                    disabled={page + 1 === (ir?.pages.length || 0)}
                    onClick={() => setPage(page + 1)}
                  >
                    <ChevronRight size={17} />
                  </button>
                  <span className="classification">
                    {ir?.pages[page]?.classification}
                  </span>
                </div>
                <div>
                  <LockKeyhole size={12} />
                  <small>Linked view</small>
                  <span className="divider" />
                  <button
                    aria-label="Zoom out"
                    onClick={() => setZoom(Math.max(0.35, zoom - 0.1))}
                  >
                    <Minus size={15} />
                  </button>
                  <span>{Math.round(zoom * 100)}%</span>
                  <button
                    aria-label="Zoom in"
                    onClick={() => setZoom(Math.min(2, zoom + 0.1))}
                  >
                    <Plus size={15} />
                  </button>
                </div>
              </div>
              <div className="preview-grid">
                <Preview
                  label="Original"
                  url={`${API}/documents/${job.id}/pdf`}
                  page={page}
                  zoom={zoom}
                  regions={ir?.pages[page]}
                  selected={selected}
                  onSelect={select}
                  scrollRef={leftScroll}
                  onScroll={(e) => linkedScroll(e, rightScroll.current)}
                />
                <Preview
                  label="English"
                  url={
                    job.output_available
                      ? `${API}/jobs/${job.id}/export/pdf?v=${job.updated_at}`
                      : undefined
                  }
                  page={page}
                  zoom={zoom}
                  regions={ir?.pages[page]}
                  selected={selected}
                  onSelect={select}
                  scrollRef={rightScroll}
                  onScroll={(e) => linkedScroll(e, leftScroll.current)}
                />
              </div>
              <div className="review-panel">
                <div className="review-tabs">
                  <button
                    className={tab === "regions" ? "chosen" : ""}
                    onClick={() => setTab("regions")}
                  >
                    Region review <span>{ir?.pages[page]?.blocks.length}</span>
                  </button>
                  <button
                    className={tab === "quality" ? "chosen" : ""}
                    onClick={() => setTab("quality")}
                  >
                    Quality report{" "}
                    <span>
                      {qa.filter((d) => d.severity !== "pass").length}
                    </span>
                  </button>
                  <div className="export-links">
                    {job.output_available && (
                      <>
                        <a href={`${API}/jobs/${job.id}/export/pdf`} download>
                          <Download size={14} />
                          English PDF
                        </a>
                        <a href={`${API}/jobs/${job.id}/export/latex`} download>
                          LaTeX bundle
                        </a>
                      </>
                    )}
                    {qa.length > 0 && (
                      <a href={`${API}/jobs/${job.id}/export/qa`} download>
                        QA JSON
                      </a>
                    )}
                  </div>
                </div>
                {tab === "quality" ? (
                  <div className="quality-list">
                    {qa.length ? (
                      qa
                        .slice()
                        .sort(
                          (a, b) =>
                            [
                              "failed",
                              "needs_review",
                              "warning",
                              "pass",
                            ].indexOf(a.severity) -
                            [
                              "failed",
                              "needs_review",
                              "warning",
                              "pass",
                            ].indexOf(b.severity),
                        )
                        .map((d, i) => (
                          <button
                            key={i}
                            className={`diagnostic ${d.severity}`}
                            onClick={() => {
                              if (d.page !== null) setPage(d.page);
                              const b = ir?.pages
                                .flatMap((p) => p.blocks)
                                .find((b) => b.id === d.block_id);
                              if (b) select(b);
                            }}
                          >
                            <span>{d.severity.replaceAll("_", " ")}</span>
                            <strong>
                              {d.page !== null ? `Page ${d.page + 1} · ` : ""}
                              {d.check.replaceAll("_", " ")}
                            </strong>
                            <p>{d.message}</p>
                          </button>
                        ))
                    ) : (
                      <p>
                        Quality checks appear after translation or rebuilding.
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="editor-grid">
                    <div className="region-list">
                      {ir?.pages[page]?.blocks.map((b) => (
                        <button
                          className={selected === b.id ? "selected" : ""}
                          key={b.id}
                          onClick={() => select(b)}
                        >
                          <small>
                            {b.role.replace("_", " ")} · {b.protection_mode}
                          </small>
                          <span>{b.source}</span>
                        </button>
                      ))}
                    </div>
                    {block ? (
                      <div className="segment-editor">
                        <div className="editor-columns">
                          <label>
                            JAPANESE SOURCE
                            <div className="source-text" lang="ja">
                              {block.source}
                            </div>
                            <small>
                              Extraction{" "}
                              {Math.round(block.source_confidence * 100)}% ·
                              Segmentation{" "}
                              {Math.round(block.segmentation_confidence * 100)}%
                            </small>
                          </label>
                          <label>
                            ENGLISH TRANSLATION
                            <textarea
                              value={draft}
                              disabled={busy}
                              onChange={(e) => setDraft(e.target.value)}
                              placeholder="Edit the translation here"
                            />
                          </label>
                        </div>
                        <div className="editor-controls">
                          <label>
                            Region{" "}
                            <select
                              value={mode}
                              disabled={busy}
                              onChange={(e) => setMode(e.target.value)}
                            >
                              <option value="translate">Translate</option>
                              <option value="protect">Protect</option>
                              <option value="ignore">Ignore</option>
                            </select>
                          </label>
                          <label>
                            Order{" "}
                            <input
                              className="order-input"
                              type="number"
                              min="0"
                              value={order}
                              onChange={(e) => setOrder(Number(e.target.value))}
                            />
                          </label>
                          <input
                            className="reason-input"
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            placeholder="Reason for protection override"
                          />
                          <button
                            className="primary"
                            disabled={busy || working}
                            onClick={() =>
                              void run(async () => {
                                await api(
                                  `/jobs/${job.id}/segments/${block.id}`,
                                  {
                                    method: "PATCH",
                                    headers: {
                                      "Content-Type": "application/json",
                                    },
                                    body: JSON.stringify({
                                      target: draft,
                                      protection_mode: mode,
                                      reading_order: order,
                                      reason,
                                    }),
                                  },
                                );
                                setIR(await api<IR>(`/documents/${job.id}`));
                                setJob(
                                  await api<Job>(`/jobs/${job.id}/rebuild`, {
                                    method: "POST",
                                  }),
                                );
                              })
                            }
                          >
                            Save & rebuild
                          </button>
                        </div>
                        {block.warnings.map((w) => (
                          <p className="region-warning" key={w}>
                            <CircleAlert size={13} />
                            {w.replaceAll("_", " ")}
                          </p>
                        ))}
                      </div>
                    ) : (
                      <div className="editor-placeholder">
                        <span>Click a highlighted region on either page.</span>
                        <p>
                          Review its source, edit the English, or protect
                          content.
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
          <footer>
            <span>
              KizunaPDF <span className="muted">/</span> Phase 1
            </span>
            <span>Japanese → English · Powered locally by MLX + XeLaTeX</span>
          </footer>
        </div>
      </main>
      {setup && (
        <div className="modal-backdrop" onClick={() => setSetup(false)}>
          <section
            className="setup-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Environment checks"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label="Close setup"
              onClick={() => setSetup(false)}
            >
              <X size={20} />
            </button>
            <span className="section-eyebrow">LOCAL ENVIRONMENT</span>
            <h2>A little setup. Then entirely offline.</h2>
            <p>
              These checks run on your Mac. Model download is the only network
              action below.
            </p>
            <div className="check-list">
              {checks.map((c) => (
                <div key={c.name}>
                  {c.ready ? (
                    <Check className="good" size={17} />
                  ) : (
                    <CircleAlert className="amber" size={17} />
                  )}
                  <div>
                    <strong>{c.name}</strong>
                    <small>{c.detail}</small>
                    {!c.ready && c.fix && <code>{c.fix}</code>}
                  </div>
                </div>
              ))}
            </div>
            <button
              className="secondary"
              onClick={() => void run(refreshChecks)}
            >
              <RefreshCw size={14} />
              Run checks
            </button>
            {!modelReady && (
              <div className="model-setup">
                <strong>TranslateGemma 4B · ~2.2 GB</strong>
                <p>
                  Model weights are licensed separately under the{" "}
                  <a
                    href="https://ai.google.dev/gemma/terms"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Gemma Terms
                  </a>
                  .
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={accepted}
                    onChange={(e) => setAccepted(e.target.checked)}
                  />
                  I have reviewed and accepted the Gemma Terms.
                </label>
                <button
                  className="primary"
                  disabled={!accepted || downloading}
                  onClick={() =>
                    void run(async () => {
                      await api("/models/download", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ accepted_terms: true }),
                      });
                      setDownloading(true);
                    })
                  }
                >
                  {downloading ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <Download size={16} />
                  )}{" "}
                  {downloading
                    ? `Downloading · ${(downloadBytes / 1e9).toFixed(2)} GB on disk`
                    : "Download model"}
                </button>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
