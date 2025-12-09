#!/usr/bin/env python3
# app.py — simple Groq proxy with health-check + CORS + robust error handling

import os
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import requests

PORT = int(os.environ.get("PORT", "10000"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
# NOTE: verify the correct Groq URL for your account; common values: api.groq.ai or api.groq.com
GROQ_URL = os.environ.get("GROQ_URL", "https://api.groq.ai/v1/chat/completions")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("groq-proxy")


class ProxyHandler(BaseHTTPRequestHandler):
    def _set_common_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status: int, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._set_common_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Health check / root (GET /)
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self._set_common_headers()
            self.end_headers()
            self.wfile.write(b"OK")
            return

        # If someone GETs the API route, return useful message
        if parsed.path == "/v1/chat/completions":
            self._send_json(200, {"message": "POST this endpoint with a JSON body to proxy to Groq."})
            return

        # Unknown GET path
        self._send_json(404, {"error": "Not Found"})

    # CORS preflight
    def do_OPTIONS(self):
        self.send_response(204)
        self._set_common_headers()
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/v1/chat/completions":
            self._send_json(404, {"error": "Not Found"})
            return

        if not GROQ_API_KEY:
            logger.error("GROQ_API_KEY not set in environment")
            self._send_json(500, {"error": "Server misconfigured", "detail": "Missing GROQ_API_KEY environment variable"})
            return

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
        body_text = body_bytes.decode("utf-8") if body_bytes else ""
        logger.info("📩 Incoming request: %s", body_text[:2000])

        # Try to parse JSON (but still forward raw if parsing fails)
        try:
            payload = json.loads(body_text) if body_text else {}
        except Exception as e:
            logger.warning("Bad JSON from client, forwarding raw body: %s", e)
            payload = None  # will use raw body_text in requests.post

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            logger.info("🚀 Forwarding to Groq: %s", GROQ_URL)
            # use json param if parsed OK, else raw text via data
            if payload is not None:
                upstream = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
            else:
                upstream = requests.post(GROQ_URL, headers=headers, data=body_text.encode("utf-8"), timeout=30)
        except requests.RequestException as e:
            logger.exception("Upstream request failed")
            self._send_json(502, {"error": "Upstream request failed", "detail": str(e)})
            return

        # Try to mirror upstream response
        status = upstream.status_code
        content_type = upstream.headers.get("Content-Type", "application/json")

        # If upstream returns JSON, forward JSON; otherwise forward raw bytes with appropriate content-type
        if content_type and "application/json" in content_type.lower():
            try:
                resp_json = upstream.json()
            except ValueError:
                # malformed JSON
                logger.warning("Upstream returned invalid JSON; returning raw text")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain")
                self._set_common_headers()
                self.end_headers()
                self.wfile.write(upstream.content)
                return

            # Log but limit size
            logger.info("📨 Groq responded: %s", json.dumps(resp_json)[:2000])
            self._send_json(status, resp_json)
            return
        else:
            # Non-JSON response: forward bytes and content-type
            logger.info("📨 Groq responded with content-type=%s, length=%d", content_type, len(upstream.content))
            self.send_response(status)
            if content_type:
                self.send_header("Content-Type", content_type)
            else:
                self.send_header("Content-Type", "application/octet-stream")
            self._set_common_headers()
            self.send_header("Content-Length", str(len(upstream.content)))
            self.end_headers()
            self.wfile.write(upstream.content)
            return


def run():
    server_address = ("0.0.0.0", PORT)
    httpd = HTTPServer(server_address, ProxyHandler)
    logger.info("🌍 Server online at port %d", PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()
