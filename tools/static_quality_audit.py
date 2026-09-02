from __future__ import annotations

import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "pilot-v1"
OUT = ROOT / "qa-static-artifacts"
OUT.mkdir(exist_ok=True)

findings: list[dict] = []
checks: list[dict] = []


def finding(severity: str, area: str, title: str, detail: str, file: str = "") -> None:
    findings.append(
        {
            "severity": severity,
            "area": area,
            "title": title,
            "detail": detail,
            "file": file,
        }
    )


def check(name: str, ok: bool, detail: str, severity: str = "major", file: str = "") -> None:
    checks.append(
        {"name": name, "ok": bool(ok), "detail": detail, "severity": severity, "file": file}
    )
    if not ok:
        finding(severity, "static-check", name, detail, file)


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.refs: list[tuple[str, str]] = []
        self.forms: list[dict] = []
        self.inputs: list[dict] = []
        self.labels_for: set[str] = set()
        self.inline_scripts = 0
        self.inline_styles = 0
        self._script_src: str | None = None
        self._style_depth = 0

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: v or "" for k, v in attrs_list}
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag in {"script", "img", "link", "a"}:
            key = "src" if tag in {"script", "img"} else "href"
            if attrs.get(key):
                self.refs.append((tag, attrs[key]))
        if tag == "form":
            self.forms.append(attrs)
        if tag in {"input", "select", "textarea", "button"}:
            self.inputs.append({"tag": tag, **attrs})
        if tag == "label" and attrs.get("for"):
            self.labels_for.add(attrs["for"])
        if tag == "script":
            self._script_src = attrs.get("src") or ""
            if not self._script_src:
                self.inline_scripts += 1
        if tag == "style":
            self.inline_styles += 1
            self._style_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._script_src = None
        if tag == "style" and self._style_depth:
            self._style_depth -= 1


def local_path(ref: str) -> Path | None:
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    if not ref or ref.startswith(("http://", "https://", "mailto:", "tel:", "data:", "javascript:")):
        return None
    if ref == "/":
        return FRONTEND / "home.html"
    return FRONTEND / ref.lstrip("/")


html_reports: dict[str, dict] = {}
for html_path in sorted(FRONTEND.glob("*.html")):
    rel = html_path.relative_to(ROOT).as_posix()
    text = html_path.read_text(encoding="utf-8")
    parser = DocumentParser()
    parser.feed(text)
    duplicates = {key: count for key, count in Counter(parser.ids).items() if count > 1}
    check(f"{rel}: unique element IDs", not duplicates, json.dumps(duplicates), "critical", rel)

    missing_assets = []
    for tag, ref in parser.refs:
        target = local_path(ref)
        if target is not None and not target.exists():
            missing_assets.append({"tag": tag, "ref": ref, "target": target.relative_to(ROOT).as_posix()})
    check(f"{rel}: referenced local assets exist", not missing_assets, json.dumps(missing_assets), "critical", rel)

    unlabelled = []
    for control in parser.inputs:
        if control["tag"] == "button" or control.get("type") in {"hidden", "submit", "button"}:
            continue
        cid = control.get("id", "")
        if not cid:
            continue
        if cid not in parser.labels_for and not control.get("aria-label") and not control.get("aria-labelledby"):
            unlabelled.append(cid)
    check(f"{rel}: form controls have programmatic labels", not unlabelled, json.dumps(unlabelled), "major", rel)

    hardcoded_versions = sorted(set(re.findall(r"[?&]v=([^\"'&\s>]+)", text)))
    stale_versions = [v for v in hardcoded_versions if v != "__PILOT_BUILD__"]
    if stale_versions:
        finding(
            "major",
            "cache-integrity",
            "Hardcoded asset version bypasses the active build token",
            f"versions={stale_versions}",
            rel,
        )

    if html_path.name in {"home.html", "index.html", "demonstracao.html", "account.html"}:
        check(
            f"{rel}: build placeholder is used for versioned assets",
            not stale_versions,
            json.dumps(stale_versions),
            "major",
            rel,
        )

    html_reports[rel] = {
        "ids": len(parser.ids),
        "forms": len(parser.forms),
        "controls": len(parser.inputs),
        "refs": parser.refs,
        "inline_scripts": parser.inline_scripts,
        "inline_styles": parser.inline_styles,
        "hardcoded_versions": hardcoded_versions,
    }

# JavaScript hygiene and information exposure checks.
raw_uuid = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
model_terms = re.compile(r"gpt-\d|openai", re.I)
for js_path in sorted(FRONTEND.glob("*.js")):
    rel = js_path.relative_to(ROOT).as_posix()
    text = js_path.read_text(encoding="utf-8")
    literal_uuids = raw_uuid.findall(text)
    if literal_uuids:
        finding("minor", "technical-identifiers", "Literal UUID present in frontend source", ", ".join(literal_uuids[:5]), rel)
    if model_terms.search(text):
        finding("minor", "provider-coupling", "Provider/model term present in frontend source", "Search matched GPT/OpenAI string", rel)
    if "console.log(" in text:
        finding("minor", "diagnostics", "console.log remains in production frontend", "Remove or gate debug output", rel)
    if re.search(r"\b(eval|new Function)\s*\(", text):
        finding("critical", "javascript-security", "Dynamic code execution primitive present", "eval/new Function detected", rel)

# Check that the canonical public and persistent paths remain distinct.
app_js = (FRONTEND / "app.js").read_text(encoding="utf-8")
check(
    "Frontend declares exactly five user moments",
    all(f"label:'{label}'" in app_js for label in ["Contexto", "Evidência", "Decisão", "Medição", "Memória"]),
    "Expected labels not all found",
    "critical",
    "frontend/pilot-v1/app.js",
)
check(
    "Frontend declares eight persistent records",
    "Observação → Evidência → Hipótese → Alternativa → Decisão → Ação → Resultado → Aprendizagem" in app_js,
    "Canonical chain not found",
    "critical",
    "frontend/pilot-v1/app.js",
)

# Configuration/version reproducibility signals.
pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
lock_candidates = [ROOT / name for name in ("requirements.lock", "requirements.txt", "uv.lock", "poetry.lock", "Pipfile.lock")]
if not any(path.exists() for path in lock_candidates):
    finding(
        "major",
        "dependency-reproducibility",
        "No Python dependency lock/constraints file found",
        "Fresh deployments can resolve different transitive versions from the same commit.",
        "pyproject.toml",
    )
if "'unsafe-inline'" in (ROOT / "backend/app/main.py").read_text(encoding="utf-8"):
    finding(
        "minor",
        "content-security-policy",
        "CSP permits unsafe-inline scripts/styles",
        "This weakens XSS containment; account.html currently relies on inline code.",
        "backend/app/main.py",
    )

# Duplicate password reset surfaces are a drift risk.
identity = (ROOT / "backend/app/atlas_platform/identity.py").read_text(encoding="utf-8")
pilot_secure = (ROOT / "backend/app/pilot_product_secure.py").read_text(encoding="utf-8")
auth_js = (FRONTEND / "auth.js").read_text(encoding="utf-8")
if "/api/auth/password-reset/request" in identity and "/api/pilot/password-reset/request" in pilot_secure:
    finding(
        "major",
        "identity-architecture",
        "Two independent password-reset token systems coexist",
        "Canonical identity and Pilot reset tables/routes can drift; the entry page already mixes canonical request with Pilot confirmation.",
        "backend/app/atlas_platform/identity.py; backend/app/pilot_product_secure.py; frontend/pilot-v1/auth.js",
    )
check(
    "Entry reset request and confirmation use one route family",
    not (
        "/api/auth/password-reset/request" in auth_js
        and "/api/pilot/password-reset/confirm" in auth_js
    ),
    "Request uses /api/auth while confirmation uses /api/pilot",
    "major",
    "frontend/pilot-v1/auth.js",
)

# Public operational diagnostics.
capabilities = (ROOT / "backend/app/pilot_capabilities.py").read_text(encoding="utf-8")
if '@router.get("/build")' in capabilities or '@router.get("/release-state")' in capabilities:
    finding(
        "major",
        "information-exposure",
        "Build and release-state diagnostics are publicly routable",
        "They expose exact branch, commit, service/environment and database migration state without authentication.",
        "backend/app/pilot_capabilities.py",
    )

findings.sort(key=lambda f: {"critical": 0, "major": 1, "minor": 2, "info": 3}.get(f["severity"], 9))
summary = {
    "checks": len(checks),
    "passed": sum(item["ok"] for item in checks),
    "failed": sum(not item["ok"] for item in checks),
    "critical": sum(item["severity"] == "critical" for item in findings),
    "major": sum(item["severity"] == "major" for item in findings),
    "minor": sum(item["severity"] == "minor" for item in findings),
}
report = {"summary": summary, "checks": checks, "findings": findings, "html": html_reports}
(OUT / "static-quality-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
lines = [
    "# SRIS static quality audit",
    "",
    f"Checks: {summary['passed']}/{summary['checks']} passed",
    f"Findings: {summary['critical']} critical · {summary['major']} major · {summary['minor']} minor",
    "",
    "## Findings",
]
for index, item in enumerate(findings, 1):
    lines.append(f"{index}. **{item['severity'].upper()} · {item['area']} · {item['title']}** — {item['detail']} ({item['file']})")
lines.extend(["", "## Failed checks"])
for index, item in enumerate((c for c in checks if not c["ok"]), 1):
    lines.append(f"{index}. **{item['severity'].upper()} · {item['name']}** — {item['detail']}")
markdown = "\n".join(lines) + "\n"
(OUT / "static-quality-report.md").write_text(markdown, encoding="utf-8")
print("===== SRIS_STATIC_AUDIT_START =====")
print(json.dumps(summary))
print(markdown)
print("===== SRIS_STATIC_AUDIT_END =====")
