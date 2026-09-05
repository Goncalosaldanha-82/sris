from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}: {old!r}")
    return text.replace(old, new, 1)


index_path = ROOT / "site" / "index.html"
index = index_path.read_text(encoding="utf-8")
index = replace_once(
    index,
    'href="https://sris-pilot-v1-staging.up.railway.app/demonstracao"',
    'href="/demonstracao"',
    label="canonical demonstration link",
)
index = replace_once(
    index,
    '<article><span>Duração</span><strong>90 dias</strong><p>Até 3 missões, com âmbito, critérios de sucesso e condições de revisão definidos antes do arranque.</p></article>',
    '<article><span>Duração</span><strong>90 dias · 1 missão medida</strong><p>Até 3 missões estruturadas. A primeira vai até ao resultado medido, porque só assim o efeito pode ser atribuído. As restantes são estruturadas até à decisão e abrem para medição em ciclo próprio.</p></article>',
    label="pilot duration",
)
for required in (
    '<link rel="canonical" href="https://sris.io/">',
    'contact@sris.io',
    '4.800 € + IVA',
    '<strong>Contratação autónoma</strong>',
):
    if required not in index:
        raise RuntimeError(f"site invariant missing: {required}")
index_path.write_text(index, encoding="utf-8")

server_path = ROOT / "contact_server.py"
server = server_path.read_text(encoding="utf-8")
server = replace_once(
    server,
    'MAX_FORM_TIME_MS = 24 * 60 * 60 * 1_000\n',
    '''MAX_FORM_TIME_MS = 24 * 60 * 60 * 1_000
DEMO_UPSTREAM_DEFAULT = "https://sris-pilot-v1-staging.up.railway.app"
DEMO_PROXY_PATHS = {
    "/demonstracao",
    "/demonstracao/",
    "/demonstracao.css",
    "/demonstracao.js",
    "/sris-favicon.svg",
    "/api/mission-intelligence/demo/fictional/missions",
}
''',
    label="demo proxy constants",
)
server = replace_once(
    server,
    'class ContactHandler(SimpleHTTPRequestHandler):\n    server_version = "SRISWebsite/1.0"\n',
    '''class ContactHandler(SimpleHTTPRequestHandler):
    server_version = "SRISWebsite/1.0"

    @staticmethod
    def _is_demo_proxy_path(path: str) -> bool:
        return path in DEMO_PROXY_PATHS or path.startswith(
            "/api/mission-intelligence/demo/fictional/missions/"
        )

    def _proxy_demo(self, *, head_only: bool = False) -> None:
        upstream = os.environ.get("SRIS_DEMO_ORIGIN", DEMO_UPSTREAM_DEFAULT).rstrip("/")
        request_path = self.path
        if request_path.split("?", 1)[0] == "/demonstracao/":
            query = "?" + request_path.split("?", 1)[1] if "?" in request_path else ""
            request_path = "/demonstracao" + query
        request = Request(
            upstream + request_path,
            headers={
                "Accept": self.headers.get("Accept", "*/*"),
                "User-Agent": "SRIS-Site-Demo-Proxy/1.0",
            },
        )
        try:
            with urlopen(request, timeout=12) as response:
                body = response.read(4_000_000)
                status = response.status
                content_type = response.headers.get(
                    "Content-Type", "application/octet-stream"
                )
        except (HTTPError, URLError, TimeoutError) as error:
            LOGGER.error("Public demonstration proxy failed: %s", error)
            self.send_error(
                HTTPStatus.BAD_GATEWAY,
                "Demonstração temporariamente indisponível.",
            )
            return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)
''',
    label="demo proxy handler",
)
server = replace_once(
    server,
    '''        path = self.path.split("?", 1)[0]
        if path == "/health":
''',
    '''        path = self.path.split("?", 1)[0]
        if self._is_demo_proxy_path(path):
            self._proxy_demo()
            return
        if path == "/health":
''',
    label="GET routing",
)
server = replace_once(
    server,
    '''        path = self.path.split("?", 1)[0]
        if path == "/backups" or path.startswith("/backups/"):
''',
    '''        path = self.path.split("?", 1)[0]
        if self._is_demo_proxy_path(path):
            self._proxy_demo(head_only=True)
            return
        if path == "/backups" or path.startswith("/backups/"):
''',
    label="HEAD routing",
)
compile(server, str(server_path), "exec")
server_path.write_text(server, encoding="utf-8")

print("site measured-mission release applied")
