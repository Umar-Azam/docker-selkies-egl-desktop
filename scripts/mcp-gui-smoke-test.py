#!/usr/bin/env python3
"""Smoke test for Selkies desktop MCP server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    default_server = repo_root / "scripts" / "selkies_desktop_mcp_server.py"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-script", default=str(default_server))
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--username", default="ubuntu")
    parser.add_argument("--password", default="mypasswd")
    parser.add_argument("--browser", choices=("chromium", "firefox"), default="chromium")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--output-dir", default="/tmp/selkies-mcp-smoke")
    return parser.parse_args()


def extract_payload(result: Any) -> dict[str, Any]:
    payload = getattr(result, "structuredContent", None)
    if isinstance(payload, dict):
        return payload
    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                maybe_json = json.loads(text)
                if isinstance(maybe_json, dict):
                    return maybe_json
            except json.JSONDecodeError:
                return {"text": text}
    return {}


async def run_smoke_test(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stderr_log = output_dir / "server-stderr.log"

    server_params = StdioServerParameters(
        command="python",
        args=[
            args.server_script,
            "--url",
            args.url,
            "--username",
            args.username,
            "--password",
            args.password,
            "--browser",
            args.browser,
            "--output-dir",
            str(output_dir),
        ],
    )

    required_tools = {
        "status",
        "wait_for_stream",
        "capture_screenshot",
        "click",
        "move_mouse",
        "type_text",
        "press_key",
    }

    with stderr_log.open("w", encoding="utf-8") as errlog:
        async with stdio_client(server_params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools_result = await session.list_tools()
                tool_names = {tool.name for tool in tools_result.tools}
                missing_tools = sorted(required_tools - tool_names)
                if missing_tools:
                    raise RuntimeError(f"missing expected tools: {', '.join(missing_tools)}")

                wait_result = await session.call_tool(
                    "wait_for_stream", {"timeout_seconds": args.timeout_seconds}
                )
                wait_payload = extract_payload(wait_result)
                if not wait_payload.get("success"):
                    raise RuntimeError(f"stream did not connect: {wait_payload}")

                status_result = await session.call_tool("status")
                status_payload = extract_payload(status_result)
                videos = status_payload.get("videos") or []
                first_video = videos[0] if videos else {}
                video_width = int(first_video.get("w", 0))
                video_height = int(first_video.get("h", 0))
                if video_width <= 0 or video_height <= 0:
                    raise RuntimeError(f"invalid video size in status payload: {status_payload}")

                shot_result = await session.call_tool(
                    "capture_screenshot", {"label": "mcp-smoke", "region": "desktop"}
                )
                shot_payload = extract_payload(shot_result)
                screenshot_path = shot_payload.get("path")
                if not screenshot_path:
                    raise RuntimeError(f"screenshot path missing from payload: {shot_payload}")
                shot_file = Path(screenshot_path)
                if not shot_file.exists() or shot_file.stat().st_size <= 0:
                    raise RuntimeError(f"screenshot file missing or empty: {shot_file}")

                center_x = video_width // 2
                center_y = video_height // 2
                await session.call_tool("move_mouse", {"x": center_x, "y": center_y})
                await session.call_tool("click", {"x": center_x, "y": center_y})
                await session.call_tool("type_text", {"text": "mcp smoke test", "delay_ms": 5})
                await session.call_tool("press_key", {"key": "Enter"})

                return {
                    "success": True,
                    "tools": sorted(tool_names),
                    "video": {"width": video_width, "height": video_height},
                    "screenshot": str(shot_file),
                    "server_stderr_log": str(stderr_log),
                }


def main() -> int:
    args = parse_args()
    result = anyio.run(run_smoke_test, args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
