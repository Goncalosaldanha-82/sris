from pathlib import Path

index_path = Path("site/index.html")
index = index_path.read_text(encoding="utf-8")
old_email = '<span class="contact-email">contact@sris.io</span>'
new_email = '<span class="contact-email" data-contact-email aria-label="Endereço de contacto institucional"></span><noscript><span class="contact-email">contact<span aria-hidden="true">@</span>sris.io</span></noscript>'
if index.count(old_email) != 1:
    raise RuntimeError(f"Expected exactly one literal contact email, found {index.count(old_email)}")
index = index.replace(old_email, new_email, 1)
old_script = '<script src="/site.js?v=202608-commercial-contact" defer></script>'
new_script = '<script src="/site.js?v=20260905-human-contact-v2" defer></script>'
if index.count(old_script) != 1:
    raise RuntimeError(f"Expected exactly one site.js version marker, found {index.count(old_script)}")
index = index.replace(old_script, new_script, 1)
index_path.write_text(index, encoding="utf-8")

js_path = Path("site/site.js")
js = js_path.read_text(encoding="utf-8")
marker = '  "use strict";\n\n'
email_bootstrap = '''  "use strict";\n\n  const institutionalEmail = ["contact", "sris.io"].join("@");\n  document.querySelectorAll("[data-contact-email]").forEach((element) => {\n    element.textContent = institutionalEmail;\n    element.setAttribute("aria-label", institutionalEmail);\n  });\n\n'''
if marker not in js:
    raise RuntimeError("site.js strict-mode marker not found")
if "institutionalEmail" in js:
    raise RuntimeError("Human-readable email bootstrap already present")
js = js.replace(marker, email_bootstrap, 1)
js_path.write_text(js, encoding="utf-8")

test_path = Path("test_contact_server.py")
tests = test_path.read_text(encoding="utf-8")
assertion_marker = '        self.assertIn("Até 3 missões estruturadas", page)\n'
new_assertions = assertion_marker + '''        self.assertIn("data-contact-email", page)\n        self.assertNotIn("contact@sris.io", page)\n        script = Path("site/site.js").read_text(encoding="utf-8")\n        self.assertIn('["contact", "sris.io"].join("@")', script)\n'''
if tests.count(assertion_marker) != 1:
    raise RuntimeError(f"Expected one site-alignment assertion marker, found {tests.count(assertion_marker)}")
tests = tests.replace(assertion_marker, new_assertions, 1)
test_path.write_text(tests, encoding="utf-8")

print("Human-readable contact rendering applied")