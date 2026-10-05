"""CORS policy tests for the dashboard (US-DASH-012).

Needs the app's runtime deps (fastapi, httpx, jinja2). Skipped if they are missing.

Run from the repo root:  python -m unittest discover -s tests -v
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

try:
    from starlette.middleware.cors import CORSMiddleware
    from starlette.testclient import TestClient
    HAVE_DEPS = True
except ImportError:  # pragma: no cover
    HAVE_DEPS = False

SERVER_PATH = Path(__file__).resolve().parent.parent / "src" / "dashboard_server.py"
ALLOWED = "https://hermes.chickentightslabs.com"
EVIL = "https://evil.example"


def load_server():
    spec = importlib.util.spec_from_file_location("dashboard_server_cors_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cors_options(app) -> dict:
    """Return the kwargs the CORSMiddleware was registered with."""
    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            return getattr(mw, "kwargs", None) or getattr(mw, "options")
    raise AssertionError("CORSMiddleware is not installed")


@unittest.skipUnless(HAVE_DEPS, "fastapi/httpx not installed")
class CorsPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server()
        # Point at a missing DB: CORS headers are added by middleware regardless of
        # whether the route succeeds, and the preflight never reaches the route.
        cls.server.KANBAN_DB = str(Path(tempfile.gettempdir()) / "does-not-exist.db")
        cls.client = TestClient(cls.server.app, raise_server_exceptions=False)

    def get(self, origin):
        return self.client.get("/health", headers={"Origin": origin})

    def test_wildcard_is_never_combined_with_credentials(self):
        opts = cors_options(self.server.app)
        if opts.get("allow_credentials"):
            self.assertNotIn("*", opts["allow_origins"])

    def test_no_wildcard_in_allowlist(self):
        self.assertNotIn("*", cors_options(self.server.app)["allow_origins"])

    def test_credentials_are_off(self):
        self.assertFalse(cors_options(self.server.app)["allow_credentials"])

    def test_known_origin_is_allowed(self):
        resp = self.get(ALLOWED)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), ALLOWED)

    def test_local_origins_are_allowed(self):
        for origin in ("http://localhost:8081", "http://127.0.0.1:8081"):
            with self.subTest(origin=origin):
                resp = self.get(origin)
                self.assertEqual(resp.headers.get("access-control-allow-origin"), origin)

    def test_unknown_origin_gets_no_cors_headers(self):
        resp = self.get(EVIL)
        self.assertNotIn("access-control-allow-origin", resp.headers)
        self.assertNotIn("access-control-allow-credentials", resp.headers)

    def test_known_origin_never_gets_credentials_header(self):
        resp = self.get(ALLOWED)
        self.assertNotIn("access-control-allow-credentials", resp.headers)

    def test_preflight_from_unknown_origin_is_rejected(self):
        resp = self.client.options("/api/state", headers={
            "Origin": EVIL, "Access-Control-Request-Method": "GET"})
        self.assertNotIn("access-control-allow-origin", resp.headers)
        self.assertEqual(resp.status_code, 400)

    def test_preflight_from_known_origin_is_allowed(self):
        resp = self.client.options("/api/state", headers={
            "Origin": ALLOWED, "Access-Control-Request-Method": "GET"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), ALLOWED)

    def test_similar_looking_origins_are_rejected(self):
        for origin in (
            "https://hermes.chickentightslabs.com.evil.example",
            "http://hermes.chickentightslabs.com",
            "https://evilhermes.chickentightslabs.com",
        ):
            with self.subTest(origin=origin):
                self.assertNotIn("access-control-allow-origin", self.get(origin).headers)


if __name__ == "__main__":
    unittest.main()
