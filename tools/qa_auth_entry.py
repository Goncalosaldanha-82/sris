"""Offline Chromium regression for SRIS entry form and asset versioning.

Uses real repository HTML/JS and rendering/middleware functions, with mocked
asynchronous fetch responses and storage. No network, databases, SRIS requests,
invitations or emails. It does not claim to test the browser HTTP cache itself.
Run: python tools/qa_auth_entry.py --chromium /usr/bin/chromium
Playwright is a test-environment requirement only.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "pilot-v1"
BUILD = "pilot-commercial-access-lifecycle-v40"
MESSAGE = "Pedido recebido. O acesso é analisado pelo SRIS. Se for aprovado, receberá um convite pessoal e de utilização única por email."


def load_function(name: str):
    module = ast.parse((ROOT / "backend" / "app" / "main.py").read_text())
    function = next(n for n in module.body if getattr(n, "name", None) == name)
    function.decorator_list = []
    namespace = {
        "FRONTEND_DIR": FRONTEND, "PILOT_BUILD": BUILD,
        "sha256": sha256, "Request": object, "uuid4": uuid4,
        "set_active_organization_id": lambda _: None,
        "reset_active_organization_id": lambda _: None,
        "safe_track_request": lambda *a, **k: None,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "main.py", "exec"), namespace)
    return namespace[name]


def run(chromium: str) -> dict:
    render = load_function("_frontend_html")
    current = (FRONTEND / "auth.js").read_text()
    broken = current.replace(
        "e.preventDefault();const form=e.currentTarget;submit(form,'A enviar pedido…'",
        "e.preventDefault();submit(e.currentTarget,'A enviar pedido…'",
    ).replace("form.reset();msg(d.message", "e.currentTarget.reset();msg(d.message")
    assert current != broken
    html = render("home.html")
    src = re.search(r'<script src="([^"]*auth\.js[^\"]*)"', html).group(1)
    expected = f"/auth.js?v={BUILD}-{sha256(current.encode()).hexdigest()[:16]}"
    assert src == expected
    assert src != f"/auth.js?v={BUILD}"
    results = [{"test": "home_references_content_fingerprinted_auth_not_old_url", "passed": True}]
    with TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "home.html").write_text((FRONTEND / "home.html").read_text())
        (folder / "auth.js").write_text(current + "\n// test changed content\n")
        render.__globals__["FRONTEND_DIR"] = folder
        assert src not in render("home.html")
        render.__globals__["FRONTEND_DIR"] = FRONTEND
    results.append({"test": "future_script_edit_changes_url_without_release_label_change", "passed": True})

    # Keep the form DOM unchanged; omit external resource loading in offline QA.
    offline_html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S)
    offline_html = re.sub(r'<link\b[^>]*>', '', offline_html)
    offline_html = re.sub(r'\bsrc="[^"]*"', '', offline_html)
    bootstrap = """(message) => {
        const store = new Map();
        Object.defineProperty(window, 'localStorage', {value: {
          getItem: k => store.get(k) || null, setItem: (k,v) => store.set(k,v),
          removeItem: k => store.delete(k)
        }, configurable: true});
        window.__qa = {calls: [], code: 202, message};
        window.fetch = async (url, options={}) => {
          window.__qa.calls.push({url, method:options.method || 'GET'});
          await new Promise(resolve => setTimeout(resolve, 120));
          if(url==='/api/pilot/capabilities')return new Response(JSON.stringify({
            account_creation:'approval_then_invitation',password_reset_delivery:'email'
          }),{status:200});
          if(url==='/api/auth/login')return new Response(JSON.stringify({detail:'Invalid credentials'}),{status:401});
          if(url==='/api/auth/password-reset/request')return new Response(JSON.stringify({message:'Pedido aceite.'}),{status:202});
          return new Response(JSON.stringify(window.__qa.code===202 ? {
            status:'accepted',message:window.__qa.message
          } : {detail:'fixture'}),{status:window.__qa.code});
        };
    }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium, headless=True, args=["--no-sandbox"])
        version = browser.version

        def new_page(script):
            page = browser.new_page()
            page.set_content(offline_html)
            page.add_style_tag(content=".hidden{display:none}")
            page.evaluate(bootstrap, MESSAGE)
            page.add_script_tag(content=script)
            page.wait_for_function("document.querySelector('#register-tab').title.length > 0")
            return page

        def submit(page):
            page.locator("#register-tab").click()
            page.locator("#reg-name").fill("QA Browser")
            page.locator("#reg-org").fill("QA Offline")
            page.locator("#reg-email").fill("qa@example.com")
            page.locator("#register-submit").click()
            page.wait_for_function("document.querySelector('#register-form').getAttribute('aria-busy') === 'false'")
            return page.locator("#message").inner_text()

        original = new_page(broken)
        message = submit(original)
        assert "Cannot read properties of null" in message and "reset" in message
        results.append({"test": "original_reset_error_reproduced_after_async_202", "passed": True})
        original.close()
        page = new_page(current)
        assert submit(page) == MESSAGE
        assert all(page.locator(selector).input_value() == "" for selector in ("#reg-name", "#reg-org", "#reg-email"))
        assert page.locator("#message").get_attribute("class") == "alert success"
        results.append({"test": "corrected_script_displays_success_and_resets_form", "passed": True})
        for code, expected_text in ((503, "O serviço não conseguiu"), (429, "Demasiadas tentativas")):
            page.evaluate("code => window.__qa.code=code", code)
            assert expected_text in submit(page)
            assert page.locator("#reg-email").input_value() == "qa@example.com"
            assert page.locator("#register-submit").is_enabled()
            results.append({"test": f"http_{code}_retains_input_and_restores_button", "passed": True})
        page.evaluate("window.__qa.code=202")
        assert submit(page) == MESSAGE
        results.append({"test": "retry_after_failure_succeeds", "passed": True})
        before = page.evaluate("window.__qa.calls.length")
        page.locator("#register-submit").click()
        page.wait_for_timeout(250)
        assert page.evaluate("window.__qa.calls.length") == before
        results.append({"test": "empty_form_sends_no_request", "passed": True})
        page.locator("#login-tab").click()
        page.locator("#login-email").fill("qa@example.com")
        page.locator("#login-password").fill("not-a-real-password")
        page.locator("#login-submit").click()
        page.wait_for_function("document.querySelector('#login-form').getAttribute('aria-busy') === 'false'")
        assert page.locator("#message").inner_text() == "Email ou palavra-passe incorretos."
        results.append({"test": "login_validation_unchanged", "passed": True})
        page.locator("#forgot-link").click()
        page.locator("#reset-email").fill("qa@example.com")
        page.locator("#reset-request-submit").click()
        page.wait_for_function("document.querySelector('#reset-request-form').getAttribute('aria-busy') === 'false'")
        assert page.locator("#message").inner_text() == "Pedido aceite."
        results.append({"test": "password_reset_request_unchanged", "passed": True})
        browser.close()

    middleware = load_function("security_and_trace_headers")
    async def call_next(request):
        return SimpleNamespace(status_code=200, headers={})
    for path in ("/auth.js", "/api/auth/capabilities", "/", "/app"):
        request = SimpleNamespace(headers={}, method="GET", url=SimpleNamespace(path=path))
        response = asyncio.run(middleware(request, call_next))
        assert "no-store" in response.headers["Cache-Control"]
        assert "immutable" not in response.headers["Cache-Control"]
    results.append({"test": "actual_middleware_does_not_cache_entry_or_javascript", "passed": True})
    return {"browser": f"Chromium {version}", "scope": "offline DOM and actual entry JS; asynchronous API fixtures; no real HTTP cache test or SRIS writes", "auth_sha256": sha256(current.encode()).hexdigest(), "auth_url": src, "passed": len(results), "failed": 0, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = run(args.chromium)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
