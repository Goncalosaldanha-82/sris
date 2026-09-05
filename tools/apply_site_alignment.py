from __future__ import annotations

from pathlib import Path


index_path = Path("site/index.html")
page = index_path.read_text(encoding="utf-8")

old_demo = 'href="https://sris-pilot-v1-staging.up.railway.app/demonstracao">Ver demonstração para alojamento'
new_demo = 'href="/demonstracao">Ver demonstração para alojamento'
if page.count(old_demo) != 1:
    raise RuntimeError(f"Expected one old demo link, found {page.count(old_demo)}")
page = page.replace(old_demo, new_demo, 1)

old_duration = '<article><span>Duração</span><strong>90 dias</strong><p>Até 3 missões, com âmbito, critérios de sucesso e condições de revisão definidos antes do arranque.</p></article>'
new_duration = '<article><span>Duração</span><strong>90 dias · 1 missão medida</strong><p>Até 3 missões estruturadas. A primeira vai até ao resultado medido, porque só assim o efeito pode ser atribuído. As restantes são estruturadas até à decisão e abrem para medição em ciclo próprio.</p></article>'
if page.count(old_duration) != 1:
    raise RuntimeError(f"Expected one duration card, found {page.count(old_duration)}")
page = page.replace(old_duration, new_duration, 1)
index_path.write_text(page, encoding="utf-8")

server_path = Path("contact_server.py")
server = server_path.read_text(encoding="utf-8")
old_get = '''        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/backups" or path.startswith("/backups/"):
'''
new_get = '''        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/demonstracao":
            self._redirect_demo()
            return
        if path == "/backups" or path.startswith("/backups/"):
'''
if server.count(old_get) != 1:
    raise RuntimeError(f"Expected one GET route marker, found {server.count(old_get)}")
server = server.replace(old_get, new_get, 1)

old_head = '''        path = self.path.split("?", 1)[0]
        if path == "/backups" or path.startswith("/backups/"):
'''
new_head = '''        path = self.path.split("?", 1)[0]
        if path == "/demonstracao":
            self._redirect_demo()
            return
        if path == "/backups" or path.startswith("/backups/"):
'''
if server.count(old_head) != 1:
    raise RuntimeError(f"Expected one HEAD route marker, found {server.count(old_head)}")
server = server.replace(old_head, new_head, 1)

marker = '''    def _redirect_www(self) -> bool:
'''
redirect_method = '''    def _redirect_demo(self) -> None:
        target = os.environ.get(
            "SRIS_PUBLIC_DEMO_URL", "https://app.sris.io/demonstracao"
        ).strip()
        if not target.startswith("https://"):
            target = "https://app.sris.io/demonstracao"
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", target)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

'''
if marker not in server:
    raise RuntimeError("Redirect method marker not found")
server = server.replace(marker, redirect_method + marker, 1)
server_path.write_text(server, encoding="utf-8")

test_path = Path("test_contact_server.py")
tests = test_path.read_text(encoding="utf-8")
old_assertions = '''        self.assertIn("Ver demonstração para alojamento", page)
        self.assertIn("Condições definidas antes do início", page)
'''
new_assertions = '''        self.assertIn("Ver demonstração para alojamento", page)
        self.assertIn('href="/demonstracao"', page)
        self.assertIn("90 dias · 1 missão medida", page)
        self.assertIn("Até 3 missões estruturadas.", page)
        self.assertIn("A primeira vai até ao resultado medido", page)
        self.assertIn("As restantes são estruturadas até à decisão", page)
        self.assertIn("Condições definidas antes do início", page)
'''
if tests.count(old_assertions) != 1:
    raise RuntimeError("Site alignment test marker not found")
tests = tests.replace(old_assertions, new_assertions, 1)
test_path.write_text(tests, encoding="utf-8")

print("Site alignment applied")
