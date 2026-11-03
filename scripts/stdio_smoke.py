"""Start the server exactly as an MCP client would (stdio) and check the handshake.

    python scripts/stdio_smoke.py            # initialize + tools/list only (no AutoCAD needed)
    python scripts/stdio_smoke.py --status   # also one read-only acad_status call
    python scripts/stdio_smoke.py -- uvx --from <source> autocad-mcp   # test an install command instead

Anything after `--` replaces the default `python -m autocad_mcp`; its stderr (install progress) is shown as is.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    command = [sys.executable, "-m", "autocad_mcp"]
    stderr = subprocess.PIPE
    if "--" in sys.argv:
        command = sys.argv[sys.argv.index("--") + 1:]
        stderr = None  # an installer can write more than a pipe holds; let it through
    proc = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=stderr, text=True, encoding="utf-8")

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def receive() -> dict:
        while True:
            line = proc.stdout.readline()
            if not line:
                raise SystemExit("server exited: " + (proc.stderr.read()[-2000:] if proc.stderr else ""))
            msg = json.loads(line)
            if "id" in msg:
                return msg

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                     "clientInfo": {"name": "smoke", "version": "0"}}})
    info = receive()["result"]["serverInfo"]
    print(f"initialize: {info['name']} {info.get('version', '')}")
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = receive()["result"]["tools"]
    print(f"tools/list: {len(tools)} tools")
    if "--status" in sys.argv[:sys.argv.index("--") if "--" in sys.argv else None]:
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "acad_status", "arguments": {}}})
        result = receive()["result"]
        text = result["content"][0]["text"]
        if result.get("isError"):
            print("acad_status error:", text)
        else:
            status = json.loads(text)
            print(f"acad_status: {status['autocad']}, {len(status['open_drawings'])} open, "
                  f"guard {status['edit_guard']}")
    proc.stdin.close()
    proc.wait(timeout=15)
    return 0 if tools else 1


if __name__ == "__main__":
    sys.exit(main())
