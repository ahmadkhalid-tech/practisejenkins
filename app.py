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

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Order API</title>
  <style>
    :root { color-scheme: light; font-family: "Segoe UI", sans-serif; background: #f4f5f7; color: #1c1e21; }
    body { margin: 0; }
    main { max-width: 640px; margin: 40px auto; padding: 0 16px 48px; }
    h1 { margin-bottom: 8px; }
    .lead { margin-top: 0; line-height: 1.5; }
    form, #result { background: #fff; border: 1px solid #d8dbe2; padding: 16px; }
    fieldset { border: 0; margin: 0 0 16px; padding: 0; }
    legend { font-weight: 600; margin-bottom: 8px; }
    label { display: block; margin-bottom: 12px; font-size: 14px; }
    input { display: block; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 8px 10px; border: 1px solid #c5c9d2; font: inherit; }
    button { background: #1f4b99; color: #fff; border: 0; padding: 10px 16px; font: inherit; cursor: pointer; }
    #result { margin-top: 20px; }
    pre { overflow: auto; background: #f7f8fa; padding: 12px; margin: 0; }
  </style>
</head>
<body>
  <main>
    <h1>Create order</h1>
    <p class="lead">This page calls <code>POST /api/orders</code>. The API requires two headers and a JSON body.</p>
    <form id="order-form">
      <fieldset>
        <legend>Headers</legend>
        <label>X-Api-Key <input id="api-key" value="demo-key" autocomplete="off" required></label>
        <label>X-Channel <input id="channel" value="WEB" autocomplete="off" required></label>
      </fieldset>
      <fieldset>
        <legend>Body</legend>
        <label>item <input id="item" value="notebook" required></label>
        <label>quantity <input id="quantity" type="number" min="1" value="2" required></label>
      </fieldset>
      <button type="submit">Send request</button>
    </form>
    <section id="result" hidden>
      <h2>Response</h2>
      <p id="result-status"></p>
      <pre id="result-body"></pre>
    </section>
  </main>
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
]


def _fail(message, status):
    return jsonify({"status": "Failed", "message": message}), status


@app.get("/")
def home():
    return PAGE


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


def run_tests():
    root = os.path.dirname(os.path.abspath(__file__))
    results_path = os.path.join(root, "test-results.json")
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
    print(json.dumps({"total": report["total"], "passed": report["passed"], "failed": report["failed"]}))
    print(f"Wrote {results_path}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(run_tests())
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5050")), debug=False)