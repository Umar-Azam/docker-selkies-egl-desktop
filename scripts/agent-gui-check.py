#!/usr/bin/env python3
"""Validate that Selkies WebRTC reaches a rendered desktop frame in browser."""

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--username", default="ubuntu")
    parser.add_argument("--password", default="mypasswd")
    parser.add_argument("--browser", choices=("chromium", "firefox"), default="chromium")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--output-dir", default="/tmp/selkies-agent-gui")
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "status.json"
    screenshot_path = out_dir / "final.png"

    deadline = time.time() + args.timeout_seconds
    states = []
    success = False

    with sync_playwright() as p:
        browser_factory = p.chromium if args.browser == "chromium" else p.firefox
        browser = browser_factory.launch(headless=True)
        ctx = browser.new_context(
            http_credentials={"username": args.username, "password": args.password},
            viewport={"width": 1600, "height": 900},
        )
        page = ctx.new_page()

        page.goto(args.url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(6000)

        while time.time() < deadline:
            state = page.evaluate(
                """() => {
                    const txt = document.body ? document.body.innerText : '';
                    const waiting = /waiting for stream/i.test(txt);
                    const m = txt.match(/Peer connection state:\\s*([^\\n]+)/i);
                    const peerState = m ? m[1].trim() : '';
                    const videos = Array.from(document.querySelectorAll('video')).map(v => ({
                      w: v.videoWidth, h: v.videoHeight, ready: v.readyState, paused: v.paused, t: v.currentTime
                    }));
                    return { waiting, peerState, videos };
                }"""
            )
            states.append(state)
            first_video = state["videos"][0] if state["videos"] else {}
            if (
                state["peerState"].lower() in {"connected", "completed"}
                and first_video.get("w", 0) > 0
                and first_video.get("h", 0) > 0
                and first_video.get("ready", 0) >= 2
            ):
                success = True
                page.wait_for_timeout(2000)
                break
            page.wait_for_timeout(2000)

        page.screenshot(path=str(screenshot_path), full_page=True)
        ctx.close()
        browser.close()

    result = {
        "success": success,
        "browser": args.browser,
        "url": args.url,
        "final": states[-1] if states else {},
        "states_tail": states[-12:],
        "screenshot": str(screenshot_path),
    }
    status_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(run())
