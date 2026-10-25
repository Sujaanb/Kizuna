# Security and privacy

Processing is local. The only application feature that accesses the network is explicit
model download. Dependency installation and optional GitHub publishing also use the
network. Translation requires an existing model folder and never auto-downloads weights.
There are no cloud inference calls, telemetry exporters, external assets, ads, or API keys.

The server binds only `127.0.0.1`. Trusted Host checks reject other hostnames. Mutating
routes require an unguessable session header and reject cross-origin browser writes.
CORS is not enabled. The local UI fetches its session token from the same origin. This
protects against ordinary cross-site browser requests and DNS rebinding, not malware
running under the same OS account. The PDF worker and scripts are served locally under
a restrictive CSP. Only allowlisted artifact names under validated UUID job directories
are downloadable. File paths are never accepted in HTTP route parameters.

Uploads default to 50 MB and 100 pages. Invalid files, forms, out-of-media crops,
nonstandard UserUnit and incorrect passwords are rejected. Passwords are entered at
runtime, not persisted. The authenticated working copy is decrypted in private job data.
Input SHA256 in the manifest describes the uploaded file, not that decrypted copy.

Private data includes source PDFs, extraction text, generated translations, OCR images,
logs, previews, sanitized backgrounds and the SQLite translation cache. Default storage
is `~/Library/Application Support/KizunaPDF`; use `KIZUNAPDF_DATA_DIR` to choose another
private location. The acceptance run in this checkout uses `.runtime/jobs`. Directories
are mode 0700 and the service starts with umask 077. Stop the app before deleting job
folders or `translations.sqlite3`. Deletion is manual in Phase 1; no cloud copy exists.

Generated LaTeX escapes PDF text and never enables shell escape. Saved TeX in exported
bundles is intentionally editable executable content: compile only your own/trusted
bundles. No-shell-escape is not a complete TeX sandbox. ZIP extraction rejects traversal,
symlinks, >500 MB uncompressed size, and >2,000 members. Malicious parser resource use
beyond ordinary input limits remains a limitation; treat untrusted PDFs with care.

Source bundles omit the original PDF, but contain source text in the IR and may retain
Japanese protected regions/artwork. They are private translation projects, not secure
redaction deliverables. This software is not a document sanitization or DRM bypass tool.

Model licenses remain separate. Download errors requiring access acceptance refer the
user to the official Hugging Face page; no gated access is bypassed. No model weights,
private documents, generated job artifacts, or personal implementation prompts are
included in Git. See `.gitignore` and the prepublication audit in the status document.
