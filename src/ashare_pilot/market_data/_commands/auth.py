#!/usr/bin/env python3
"""
Launch Chrome with CDP (Chrome DevTools Protocol), navigate to a URL, and extract cookies.
"""

import subprocess
import json
import time
import sys
import os
import argparse
import tempfile
import threading

import requests
import websocket

from ashare_pilot.http_settings import http_get


def find_chrome():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    ]
    found = [p for p in paths if os.path.exists(p)]
    if found:
        return found[0]
    raise FileNotFoundError(f"Chrome not found. Searched: {paths}")


def _read_stderr(pipe, lines_out):
    for line in pipe:
        decoded = line.decode(errors="replace").strip()
        if decoded:
            lines_out.append(decoded)


def launch_chrome(port=9222, user_data_dir=None, url=None):
    chrome = find_chrome()
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir or tempfile.mkdtemp(prefix='chrome_cdp_')}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-default-apps",
        "--disable-translate",
        "--no-service-autorun",
        "--remote-allow-origins=*",
    ]
    if url:
        args.append(url)

    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    stderr_lines = []
    t = threading.Thread(target=_read_stderr, args=(proc.stderr, stderr_lines), daemon=True)
    t.start()

    return proc, stderr_lines, t


def wait_for_cdp(port=9222, timeout=30):
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            resp = http_get(f"http://localhost:{port}/json/version", timeout=2)
            if resp.ok:
                return True
            last_err = f"HTTP {resp.status_code}"
        except requests.ConnectionError:
            last_err = "connection refused"
        except Exception as e:
            last_err = str(e)
        time.sleep(0.5)
    raise TimeoutError(
        f"Chrome CDP did not start on port {port} within {timeout}s (last: {last_err})"
    )


def get_cdp_ws_url(port=9222):
    resp = http_get(f"http://localhost:{port}/json")
    pages = resp.json()
    for page in pages:
        if page["type"] == "page":
            return page["webSocketDebuggerUrl"]
    raise RuntimeError("No page target found. Try opening a tab in Chrome.")


class CDPClient:
    def __init__(self, ws_url):
        # CDP is a localhost connection. Explicitly bypass websocket-client's
        # HTTP(S)_PROXY environment fallback.
        self.ws = websocket.create_connection(
            ws_url,
            timeout=10,
            http_no_proxy=["*"],
        )
        self._id = 0

    def send(self, method, params=None):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))
        while True:
            raw = self.ws.recv()
            if not raw:
                continue
            resp = json.loads(raw)
            if resp.get("id") == self._id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error [{method}]: {resp['error']}")
                return resp

    def wait_for_event(self, event_method, timeout=15):
        self.ws.settimeout(timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = self.ws.recv()
                if not raw:
                    continue
                msg = json.loads(raw)
                if msg.get("method") == event_method:
                    return msg
            except websocket.WebSocketTimeoutException:
                raise TimeoutError(f"Timed out waiting for event: {event_method}")
        raise TimeoutError(f"Timed out waiting for event: {event_method}")

    def close(self):
        self.ws.close()


def navigate(cdp, url):
    cdp.send("Page.enable")
    cdp.send("Page.navigate", {"url": url})
    try:
        cdp.wait_for_event("Page.loadEventFired", timeout=15)
        print("[*] Page loaded.")
    except TimeoutError:
        print("[!] Page load timed out, continuing anyway...")



def format_cookies_netscape(cookies):
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c.get("domain", "")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        expires = str(int(c.get("expires", 0))) if c.get("expires") else "0"
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
    return "\n".join(lines)


def format_cookies_simple(cookies):
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Get cookies from a website via Chrome CDP")
    parser.add_argument("url", nargs="?", default="https://www.example.com", help="Target URL")
    parser.add_argument("-o", "--output", default="cookies.json", help="Output file path (JSON)")
    parser.add_argument("--cookie-file", help="Write cookie string directly to file in KEY=VALUE format")
    parser.add_argument("-p", "--port", type=int, default=9222, help="CDP debugging port (default: 9222)")
    parser.add_argument("--user-data-dir", help="Custom Chrome user data directory (persist login state)")
    parser.add_argument("--no-launch", action="store_true", help="Connect to an already running Chrome, don't launch one")
    parser.add_argument("--auto", action="store_true", help="Skip manual verification wait, get cookies immediately")
    parser.add_argument("--txt", action="store_true", help="Also output as Netscape cookie format (cookies.txt)")
    args = parser.parse_args(argv)

    proc = None
    stderr_lines = []
    if not args.no_launch:
        print(f"[*] Launching Chrome on port {args.port} ...")
        proc, stderr_lines, _ = launch_chrome(args.port, args.user_data_dir, args.url)

    print("[*] Waiting for CDP to be ready...")
    try:
        wait_for_cdp(args.port, timeout=60)
    except TimeoutError as e:
        print(f"[!] {e}")
        if stderr_lines:
            print("[!] Chrome stderr (last 10 lines):")
            for line in stderr_lines[-10:]:
                print(f"    {line}")
        sys.exit(1)

    ws_url = get_cdp_ws_url(args.port)
    cdp = CDPClient(ws_url)

    cdp.send("Network.enable")
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")

    ready = cdp.send("Runtime.evaluate", {"expression": "document.readyState"})
    state = (ready.get("result", {}).get("result", {}).get("value", ""))
    if state == "complete":
        print("[*] Page already loaded.")
    elif state in ("loading", "interactive"):
        print("[*] Waiting for page to finish loading...")
        try:
            cdp.wait_for_event("Page.loadEventFired", timeout=15)
            print("[*] Page loaded.")
        except TimeoutError:
            print("[!] Page load timed out, continuing anyway...")
    else:
        print(f"[*] Navigating to {args.url} ...")
        navigate(cdp, args.url)

    if not args.auto:
        input("[*] 请在浏览器中完成人机验证/登录，然后按 Enter 获取 Cookie...\n")

    print("[*] Fetching all cookies (including HttpOnly from SSO redirects)...")
    result = cdp.send("Network.getCookies")
    cookies = result.get("result", {}).get("cookies", [])

    cdp.close()

    if not args.cookie_file or args.output != "cookies.json":
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)
        print(f"[+] Got {len(cookies)} cookies -> {args.output}")

    if args.txt:
        txt_path = args.output.rsplit(".", 1)[0] + ".txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(format_cookies_netscape(cookies))
        print(f"[+] Netscape format -> {txt_path}")

    if cookies:
        print(f"[*] Cookie string: {format_cookies_simple(cookies)[:200]}...")

    if args.cookie_file:
        cookie_str = format_cookies_simple(cookies)
        with open(args.cookie_file, "w", encoding="utf-8") as f:
            f.write(f"EASTMONEY_COOKIE={cookie_str}\n")
        print(f"[+] Cookie written -> {args.cookie_file}")

    if proc:
        print("[*] Closing Chrome...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[*] Chrome closed.")


if __name__ == "__main__":
    main()
