import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent import QUOTES, STOCK, THRESHOLD

ROOT = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data, content_type="application/json"):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self.respond(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/config":
            return self.respond(200, {
                "inventory": STOCK,
                "threshold": THRESHOLD,
                "quotes": QUOTES,
                "key_ready": bool(os.getenv("GROQ_API_KEY", "").strip()),
                "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            })
        self.respond(404, {"error": "Page not found."})

    def do_POST(self):
        if self.path != "/api/run":
            return self.respond(404, {"error": "Page not found."})
        if self.headers.get("Content-Type") != "application/json":
            return self.respond(415, {"error": "Expected a JSON request."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or data.get("item") not in STOCK:
                raise ValueError("Choose a supported item.")
            values = [data.get(field) for field in ("quantity", "budget", "days")]
            if any(type(value) is not int or value <= 0 or value > 10000000 for value in values):
                raise ValueError("Quantity, budget, and days must be positive whole numbers up to 10,000,000.")
            mode = data.get("mode")
            if mode not in ("live", "rehearse"):
                raise ValueError("Choose live or rehearsal mode.")
            if mode == "live" and not os.getenv("GROQ_API_KEY", "").strip():
                raise ValueError("Set GROQ_API_KEY in the terminal, then restart server.py.")
        except (ValueError, TypeError) as error:
            return self.respond(400, {"error": str(error)})

        command = [sys.executable, str(ROOT / "agent.py"), "--item", data["item"],
                   "--quantity", str(values[0]), "--budget", str(values[1]), "--days", str(values[2])]
        if mode == "rehearse":
            command.append("--rehearse")
        try:
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "utf-8"
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=260,
                                     env=environment)
        except subprocess.TimeoutExpired as error:
            partial = error.stdout or b""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            return self.respond_run(partial, "Run timed out. Check any draft shown below before retrying.", False)
        except OSError:
            return self.respond(500, {"error": "Could not start the Python agent."})
        self.respond_run(process.stdout, process.stderr.strip(), process.returncode == 0)

    def respond_run(self, output, error, success):
        events = []
        for line in output.splitlines():
            match = re.match(r"^\d+\. (\w+) -> (.*)$", line)
            if match:
                events.append({"tool": match[1], "result": json.loads(match[2])})
        decision = re.search(r"Decision \(\d+ tool calls\): ([\s\S]*)", output)
        self.respond(200, {"success": success, "events": events,
                           "decision": decision.group(1).strip() if decision else "",
                           "error": error if not success else ""})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"Open http://127.0.0.1:{port} in your browser. Press Ctrl+C to stop.", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    except OSError as error:
        sys.exit(f"Could not start server: {error}. Try a different PORT.")
