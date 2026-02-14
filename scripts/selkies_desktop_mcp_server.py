#!/usr/bin/env python3
"""MCP server for Selkies browser desktop screenshot + computer-use actions."""

from __future__ import annotations

import argparse
import atexit
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)


class SelkiesDesktopController:
    """Controls Selkies desktop through an async Playwright browser session."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        browser_name: str,
        headless: bool,
        viewport_width: int,
        viewport_height: int,
        output_dir: Path,
    ) -> None:
        self.url = url
        self.username = username
        self.password = password
        self.browser_name = browser_name
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._lock = anyio.Lock()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def close(self) -> None:
        async with self._lock:
            if self._context is not None:
                await self._context.close()
                self._context = None
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
            self._page = None

    async def _ensure_session(self) -> None:
        async with self._lock:
            if self._page is not None and not self._page.is_closed():
                return

            # Cleanup any stale state first
            if self._context is not None:
                await self._context.close()
                self._context = None
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None

            self._playwright = await async_playwright().start()
            launcher = (
                self._playwright.chromium
                if self.browser_name == "chromium"
                else self._playwright.firefox
            )
            self._browser = await launcher.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                http_credentials={"username": self.username, "password": self.password},
                viewport={"width": self.viewport_width, "height": self.viewport_height},
            )
            self._page = await self._context.new_page()
            await self._page.goto(self.url, wait_until="domcontentloaded", timeout=120000)
            await self._page.wait_for_timeout(5000)

    async def status(self) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        async with self._lock:
            state = await self._page.evaluate(
                """() => {
                    const txt = document.body ? document.body.innerText : '';
                    const waiting = /waiting for stream/i.test(txt);
                    const m = txt.match(/Peer connection state:\\s*([^\\n]+)/i);
                    const peerState = m ? m[1].trim() : '';
                    const videos = Array.from(document.querySelectorAll('video')).map(v => ({
                        w: v.videoWidth || 0,
                        h: v.videoHeight || 0,
                        ready: v.readyState || 0,
                        paused: !!v.paused,
                        t: Number(v.currentTime || 0),
                    }));
                    return { waiting, peerState, videos };
                }"""
            )
        state["url"] = self.url
        return state

    async def wait_for_stream(self, timeout_seconds: int, poll_interval_seconds: float) -> dict[str, Any]:
        deadline = anyio.current_time() + timeout_seconds
        last_state: dict[str, Any] = {}
        while anyio.current_time() < deadline:
            last_state = await self.status()
            videos = last_state.get("videos") or []
            first_video = videos[0] if videos else {}
            if (
                str(last_state.get("peerState", "")).lower() in {"connected", "completed"}
                and int(first_video.get("w", 0)) > 0
                and int(first_video.get("h", 0)) > 0
                and int(first_video.get("ready", 0)) >= 2
            ):
                return {"success": True, "state": last_state}
            await anyio.sleep(poll_interval_seconds)
        return {
            "success": False,
            "state": last_state,
            "error": f"stream did not connect within {timeout_seconds}s",
        }

    async def _video_metrics(self) -> dict[str, float]:
        await self._ensure_session()
        assert self._page is not None
        async with self._lock:
            metrics = await self._page.evaluate(
                """() => {
                    const video = document.querySelector('video');
                    if (!video) return null;
                    const rect = video.getBoundingClientRect();
                    return {
                        left: rect.left,
                        top: rect.top,
                        width: rect.width,
                        height: rect.height,
                        videoWidth: video.videoWidth || 0,
                        videoHeight: video.videoHeight || 0
                    };
                }"""
            )
        if not metrics:
            raise RuntimeError("no video element found in Selkies page")
        if metrics["videoWidth"] <= 0 or metrics["videoHeight"] <= 0:
            raise RuntimeError("video stream is not ready yet (video dimensions are zero)")
        return metrics

    async def _desktop_to_page(self, x: int, y: int) -> tuple[float, float]:
        metrics = await self._video_metrics()
        video_width = max(1, int(metrics["videoWidth"]))
        video_height = max(1, int(metrics["videoHeight"]))
        clamped_x = min(max(x, 0), video_width - 1)
        clamped_y = min(max(y, 0), video_height - 1)
        page_x = float(metrics["left"]) + (clamped_x / video_width) * float(metrics["width"])
        page_y = float(metrics["top"]) + (clamped_y / video_height) * float(metrics["height"])
        return page_x, page_y

    async def capture_screenshot(self, label: str | None, region: str) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = f"{label or 'shot'}-{ts}"
        out_path = self.output_dir / f"{stem}.png"

        async with self._lock:
            if region == "desktop":
                video = self._page.locator("video").first
                if await video.count() > 0:
                    await video.screenshot(path=str(out_path))
                else:
                    await self._page.screenshot(path=str(out_path), full_page=True)
            else:
                await self._page.screenshot(path=str(out_path), full_page=True)

        return {"path": str(out_path), "state": await self.status()}

    async def click(self, x: int, y: int, button: str, clicks: int) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        page_x, page_y = await self._desktop_to_page(x, y)
        async with self._lock:
            await self._page.mouse.click(page_x, page_y, button=button, click_count=clicks)
        return {"ok": True, "desktop": {"x": x, "y": y}, "page": {"x": page_x, "y": page_y}}

    async def move_mouse(self, x: int, y: int) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        page_x, page_y = await self._desktop_to_page(x, y)
        async with self._lock:
            await self._page.mouse.move(page_x, page_y)
        return {"ok": True, "desktop": {"x": x, "y": y}, "page": {"x": page_x, "y": page_y}}

    async def drag(
        self, start_x: int, start_y: int, end_x: int, end_y: int, steps: int
    ) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        from_x, from_y = await self._desktop_to_page(start_x, start_y)
        to_x, to_y = await self._desktop_to_page(end_x, end_y)
        async with self._lock:
            await self._page.mouse.move(from_x, from_y)
            await self._page.mouse.down()
            await self._page.mouse.move(to_x, to_y, steps=max(1, steps))
            await self._page.mouse.up()
        return {
            "ok": True,
            "from": {"desktop": [start_x, start_y], "page": [from_x, from_y]},
            "to": {"desktop": [end_x, end_y], "page": [to_x, to_y]},
        }

    async def type_text(self, text: str, delay_ms: int) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        async with self._lock:
            await self._page.keyboard.type(text, delay=max(0, delay_ms))
        return {"ok": True, "typed": len(text)}

    async def press_key(self, key: str) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        async with self._lock:
            await self._page.keyboard.press(key)
        return {"ok": True, "key": key}

    async def press_hotkey(self, keys: list[str]) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        combo = "+".join(keys)
        async with self._lock:
            await self._page.keyboard.press(combo)
        return {"ok": True, "combo": combo}

    async def scroll(self, delta_x: int, delta_y: int) -> dict[str, Any]:
        await self._ensure_session()
        assert self._page is not None
        async with self._lock:
            await self._page.mouse.wheel(delta_x, delta_y)
        return {"ok": True, "delta_x": delta_x, "delta_y": delta_y}

    async def wait(self, seconds: float) -> dict[str, Any]:
        await anyio.sleep(max(0.0, seconds))
        return {"ok": True, "slept_seconds": max(0.0, seconds)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--username", default="ubuntu")
    parser.add_argument("--password", default="mypasswd")
    parser.add_argument("--browser", choices=("chromium", "firefox"), default="chromium")
    parser.add_argument("--headed", action="store_true", help="Run browser with visible UI")
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=900)
    parser.add_argument("--output-dir", default="/tmp/selkies-mcp")
    parser.add_argument("--name", default="selkies-desktop-mcp")
    return parser.parse_args()


def build_server(controller: SelkiesDesktopController, name: str) -> FastMCP:
    mcp = FastMCP(name)

    @mcp.tool(description="Return current WebRTC/video status from Selkies web UI.")
    async def status() -> dict[str, Any]:
        return await controller.status()

    @mcp.tool(description="Wait until the remote desktop stream is connected and rendering video.")
    async def wait_for_stream(
        timeout_seconds: int = 180, poll_interval_seconds: float = 2.0
    ) -> dict[str, Any]:
        return await controller.wait_for_stream(timeout_seconds, poll_interval_seconds)

    @mcp.tool(description="Capture screenshot from Selkies page. region='desktop' crops to video element.")
    async def capture_screenshot(label: str | None = None, region: str = "desktop") -> dict[str, Any]:
        return await controller.capture_screenshot(label, region)

    @mcp.tool(description="Click on remote desktop coordinates (x, y) measured in desktop pixels.")
    async def click(x: int, y: int, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        return await controller.click(x, y, button, clicks)

    @mcp.tool(description="Move mouse cursor to remote desktop coordinates.")
    async def move_mouse(x: int, y: int) -> dict[str, Any]:
        return await controller.move_mouse(x, y)

    @mcp.tool(description="Drag mouse between remote desktop coordinates.")
    async def drag(
        start_x: int, start_y: int, end_x: int, end_y: int, steps: int = 20
    ) -> dict[str, Any]:
        return await controller.drag(start_x, start_y, end_x, end_y, steps)

    @mcp.tool(description="Type text into current remote desktop focus.")
    async def type_text(text: str, delay_ms: int = 20) -> dict[str, Any]:
        return await controller.type_text(text, delay_ms)

    @mcp.tool(description="Press a single key (for example Enter, Escape, Control+L).")
    async def press_key(key: str) -> dict[str, Any]:
        return await controller.press_key(key)

    @mcp.tool(description="Press a key combo list (for example ['Control', 'Alt', 'T']).")
    async def press_hotkey(keys: list[str]) -> dict[str, Any]:
        return await controller.press_hotkey(keys)

    @mcp.tool(description="Send mouse wheel scroll events.")
    async def scroll(delta_x: int = 0, delta_y: int = 600) -> dict[str, Any]:
        return await controller.scroll(delta_x, delta_y)

    @mcp.tool(description="Sleep helper between actions.")
    async def wait(seconds: float) -> dict[str, Any]:
        return await controller.wait(seconds)

    return mcp


def main() -> int:
    args = parse_args()
    controller = SelkiesDesktopController(
        url=args.url,
        username=args.username,
        password=args.password,
        browser_name=args.browser,
        headless=not args.headed,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        output_dir=Path(args.output_dir),
    )
    atexit.register(lambda: anyio.run(controller.close))
    mcp = build_server(controller, args.name)
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
