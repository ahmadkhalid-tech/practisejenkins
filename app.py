import html
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from flask import Flask, jsonify, request

app = Flask(__name__)

VALID_API_KEY = "demo-key"
_order_seq = 1000

SITE_CSS = """
body { margin: 0; font-family: "Segoe UI", sans-serif; background: #eef1f6; color: #1c2430; }
header { background: #16325c; color: #fff; padding: 20px 32px; }
header h1 { margin: 0; font-size: 22px; }
header p { margin: 6px 0 0; }
.wrap { max-width: 980px; margin: 24px auto 40px; padding: 0 16px; }
.stats { display: flex; gap: 12px; margin-bottom: 16px; }
.stat, .panel { background: #fff; border: 1px solid #d5dbe6; }
.stat { flex: 1; padding: 14px 18px; }
.stat b { display: block; font-size: 24px; margin-top: 4px; }
.layout { display: flex; gap: 16px; align-items: flex-start; }
.panel { padding: 18px; }
.panel.grow { flex: 2; }
.panel.side { flex: 1; }
h2 { margin: 0 0 12px; font-size: 16px; }
label { display: block; margin-bottom: 12px; font-size: 14px; }
input { display: block; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 8px 10px; border: 1px solid #c5c9d2; font: inherit; }
button { background: #16325c; color: #fff; border: 0; padding: 10px 16px; font: inherit; cursor: pointer; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #e4e8ef; }
th { background: #f4f7fb; }
.pass { color: #0d7a3f; font-weight: 700; }
.fail { color: #b42318; font-weight: 700; }
pre { overflow: auto; background: #f7f8fa; padding: 12px; margin: 0; }
.side p, .side li { line-height: 1.5; }
code { background: #f4f7fb; padding: 1px 4px; }
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Order API</title>
  <link rel="stylesheet" href="/site.css">
</head>
<body>
  <header>
    <h1>Order API</h1>
    <p>Create an order with the required headers and JSON body.</p>
  </header>
  <div class="wrap">
    <div class="layout">
      <section class="panel grow">
        <h2>Request</h2>
        <form id="order-form">
          <label>X-Api-Key <input id="api-key" value="demo-key" autocomplete="off" required></label>
          <label>X-Channel <input id="channel" value="WEB" autocomplete="off" required></label>
          <label>item <input id="item" value="notebook" required></label>
          <label>quantity <input id="quantity" type="number" min="1" value="2" required></label>
          <button type="submit">Send request</button>
        </form>
        <section id="result" hidden>
          <h2>Response</h2>
          <p id="result-status"></p>
          <pre id="result-body"></pre>
        </section>
      </section>
      <aside class="panel side">
        <h2>Contract</h2>
        <p><code>POST /api/orders</code></p>
        <ul>
          <li>Header <code>X-Api-Key</code>: demo-key</li>
          <li>Header <code>X-Channel</code>: WEB or MOBILE</li>
          <li>Body <code>item</code> and a positive <code>quantity</code></li>
        </ul>
      </aside>
    </div>
  </div>
  <script>
    const form = document.getElementById("order-form");
    const result = document.getElementById("result");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const response = await fetch("/api/orders", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": document.getElementById("api-key").value.trim(),
          "X-Channel": document.getElementById("channel").value.trim()
        },
        body: JSON.stringify({
          item: document.getElementById("item").value.trim(),
          quantity: Number(document.getElementById("quantity").value)
        })
      });
      const body = await response.json();
      result.hidden = false;
      document.getElementById("result-status").textContent = "HTTP " + response.status;
      document.getElementById("result-body").textContent = JSON.stringify(body, null, 2);
    });
  </script>
</body>
</html>
"""

TEST_CASES = [
    {
        "name": "health check",
        "method": "GET",
        "path": "/api/health",
        "headers": {},
        "body": None,
        "expect_status": 200,
        "expect_json": {"status": "ok"},
    },
    {
        "name": "create order with required headers and body",
        "method": "POST",
        "path": "/api/orders",
        "headers": {"Content-Type": "application/json", "X-Api-Key": "demo-key", "X-Channel": "WEB"},
        "body": {"item": "notebook", "quantity": 2},
        "expect_status": 201,
        "expect_json": {"status": "Success", "item": "notebook", "quantity": 2, "channel": "WEB"},
    },
    {
        "name": "reject missing X-Api-Key",
        "method": "POST",
        "path": "/api/orders",
        "headers": {"Content-Type": "application/json", "X-Channel": "WEB"},
        "body": {"item": "notebook", "quantity": 1},
        "expect_status": 401,
        "expect_json": {"status": "Failed"},
    },
    {
        "name": "reject invalid X-Api-Key",
        "method": "POST",
        "path": "/api/orders",
        "headers": {"Content-Type": "application/json", "X-Api-Key": "wrong-key", "X-Channel": "WEB"},
        "body": {"item": "notebook", "quantity": 1},
        "expect_status": 401,
        "expect_json": {"status": "Failed"},
    },
    {
        "name": "reject missing X-Channel",
        "method": "POST",
        "path": "/api/orders",
        "headers": {"Content-Type": "application/json", "X-Api-Key": "demo-key"},
        "body": {"item": "notebook", "quantity": 1},
        "expect_status": 400,
        "expect_json": {"status": "Failed", "message": "Missing X-Channel header"},
    },
    {
        "name": "reject missing item",
        "method": "POST",
        "path": "/api/orders",
        "headers": {"Content-Type": "application/json", "X-Api-Key": "demo-key", "X-Channel": "MOBILE"},
        "body": {"quantity": 1},
        "expect_status": 400,
        "expect_json": {"status": "Failed", "message": "item is required"},
    },
    {
        "name": "reject non-positive quantity",
        "method": "POST",
        "path": "/api/orders",
        "headers": {"Content-Type": "application/json", "X-Api-Key": "demo-key", "X-Channel": "WEB"},
        "body": {"item": "notebook", "quantity": 0},
        "expect_status": 400,
        "expect_json": {"status": "Failed", "message": "quantity must be a positive integer"},
    },
    {
        "name": "reject request when all parameters are missing",
        "method": "POST",
        "path": "/api/orders",
        "headers": {},
        "body": {},
        "expect_status": 401,
        "expect_json": {"status": "Failed", "message": "Invalid or missing X-Api-Key"},
    },
]


def _fail(message, status):
    return jsonify({"status": "Failed", "message": message}), status


@app.get("/")
def home():
    return PAGE


@app.get("/site.css")
def site_css():
    return SITE_CSS, 200, {"Content-Type": "text/css; charset=utf-8"}


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/orders")
def create_order():
    global _order_seq

    api_key = request.headers.get("X-Api-Key", "").strip()
    channel = request.headers.get("X-Channel", "").strip()
    if not api_key or api_key != VALID_API_KEY:
        return _fail("Invalid or missing X-Api-Key", 401)
    if not channel:
        return _fail("Missing X-Channel header", 400)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _fail("Request body must be JSON", 400)

    item = body.get("item")
    quantity = body.get("quantity")
    if not isinstance(item, str) or not item.strip():
        return _fail("item is required", 400)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return _fail("quantity must be a positive integer", 400)

    _order_seq += 1
    return jsonify(
        {
            "status": "Success",
            "orderId": f"ORD-{_order_seq}",
            "item": item.strip(),
            "quantity": quantity,
            "channel": channel,
        }
    ), 201


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_ready(base_url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.2)
    raise RuntimeError("API did not start in time")


def _call_api(base_url, case):
    data = None
    headers = dict(case["headers"])
    if case["body"] is not None:
        data = json.dumps(case["body"]).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    api_request = urllib.request.Request(
        base_url + case["path"],
        data=data,
        headers=headers,
        method=case["method"],
    )
    try:
        with urllib.request.urlopen(api_request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        return error.code, json.loads(raw) if raw else {}


def _matches(expected, actual):
    if not isinstance(expected, dict):
        return expected == actual
    if not isinstance(actual, dict):
        return False
    return all(key in actual and _matches(value, actual[key]) for key, value in expected.items())


def _xml(value):
    return html.escape(str(value), quote=True)


def _write_junit(path, results):
    failures = sum(1 for item in results if item["result"] != "passed")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="order-api" tests="{len(results)}" failures="{failures}" errors="0">',
    ]
    for item in results:
        lines.append(f'  <testcase classname="order-api" name="{_xml(item["name"])}">')
        if item["result"] != "passed":
            message = f'expected HTTP {item["expectedStatus"]}, got {item["actualStatus"]}'
            detail = json.dumps(item["response"])
            lines.append(f'    <failure message="{_xml(message)}">{_xml(detail)}</failure>')
        lines.append("  </testcase>")
    lines.append("</testsuite>")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _write_sheet(folder, report):
    os.makedirs(folder, exist_ok=True)
    rows = []
    for item in report["cases"]:
        mark = "Pass" if item["result"] == "passed" else "Fail"
        css = "pass" if mark == "Pass" else "fail"
        rows.append(
            "<tr>"
            f"<td>{html.escape(item['name'])}</td>"
            f"<td>{html.escape(item['method'])}</td>"
            f"<td>{html.escape(item['path'])}</td>"
            f"<td>{item['expectedStatus']}</td>"
            f"<td>{item['actualStatus']}</td>"
            f"<td class=\"{css}\">{mark}</td>"
            "</tr>"
        )
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Order API test cases</title>
  <link rel="stylesheet" href="site.css">
</head>
<body>
  <header>
    <h1>Order API</h1>
    <p>Test results from the Jenkins run.</p>
  </header>
  <div class="wrap">
    <div class="stats">
      <div class="stat">Total<b>{report["total"]}</b></div>
      <div class="stat">Passed<b>{report["passed"]}</b></div>
      <div class="stat">Failed<b>{report["failed"]}</b></div>
    </div>
    <section class="panel">
      <h2>Test cases</h2>
      <table>
        <thead>
          <tr><th>Case</th><th>Method</th><th>Path</th><th>Expected</th><th>Actual</th><th>Review</th></tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </section>
  </div>
</body>
</html>
"""
    html_path = os.path.join(folder, "index.html")
    css_path = os.path.join(folder, "site.css")
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(page)
    with open(css_path, "w", encoding="utf-8") as handle:
        handle.write(SITE_CSS)
    return html_path


def run_tests():
    root = os.path.dirname(os.path.abspath(__file__))
    results_path = os.path.join(root, "test-results.json")
    junit_path = os.path.join(root, "test-results.xml")
    sheet_dir = os.path.join(root, "report")
    port = _free_port()
    env = os.environ.copy()
    env["PORT"] = str(port)
    server = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__)],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_ready(base_url)
        results = []
        for case in TEST_CASES:
            status, body = _call_api(base_url, case)
            ok = status == case["expect_status"] and _matches(case["expect_json"], body)
            results.append(
                {
                    "name": case["name"],
                    "method": case["method"],
                    "path": case["path"],
                    "expectedStatus": case["expect_status"],
                    "actualStatus": status,
                    "response": body,
                    "result": "passed" if ok else "failed",
                }
            )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    passed = sum(1 for item in results if item["result"] == "passed")
    report = {
        "suite": "order-api",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "cases": results,
    }
    with open(results_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    _write_junit(junit_path, results)
    sheet_path = _write_sheet(sheet_dir, report)
    print(json.dumps({"total": report["total"], "passed": report["passed"], "failed": report["failed"]}))
    print(f"Wrote {results_path}")
    print(f"Wrote {junit_path}")
    print(f"Wrote {sheet_path}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(run_tests())
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5050")), debug=False)
