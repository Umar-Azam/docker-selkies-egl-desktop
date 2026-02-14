# Selkies Desktop MCP Setup

This guide explains how to expose the running Jetson desktop through an MCP server so another agent can:

- capture GUI screenshots
- inspect current stream status
- perform computer-use actions (mouse/keyboard)

## Prerequisites

1. Jetson desktop container is running:

```bash
./scripts/launch-jetson-desktop.sh
```

2. `codex` conda environment exists.

3. Install MCP/playwright dependencies in `codex`:

```bash
conda run -n codex pip install -r ./scripts/requirements-mcp.txt
conda run -n codex playwright install chromium firefox
```

## Start MCP Server

Run from repo root:

```bash
conda run -n codex python ./scripts/selkies_desktop_mcp_server.py \
  --url http://localhost:8080 \
  --username ubuntu \
  --password mypasswd \
  --browser chromium \
  --output-dir /tmp/selkies-mcp
```

The server uses `stdio` transport and is designed for MCP clients to spawn directly.

## Available MCP Tools

- `status`: report current WebRTC/video state
- `wait_for_stream`: block until desktop stream is connected
- `capture_screenshot`: save visible GUI screenshot to disk
- `move_mouse`, `click`, `drag`, `scroll`
- `type_text`, `press_key`, `press_hotkey`
- `wait`: timing helper between actions

Coordinate behavior:

- Mouse tools use **remote desktop pixel coordinates**.
- The server maps those coordinates to the live browser video element.

## Smoke Test

Validate end-to-end MCP functionality:

```bash
conda run -n codex python ./scripts/mcp-gui-smoke-test.py \
  --url http://localhost:8080 \
  --username ubuntu \
  --password mypasswd \
  --browser chromium
```

Expected output includes:

- `"success": true`
- non-zero video size (for example `1920x1080`)
- screenshot file path

## Example MCP Client Config (Codex-style)

```json
{
  "mcpServers": {
    "selkies-desktop": {
      "command": "conda",
      "args": [
        "run",
        "-n",
        "codex",
        "python",
        "/absolute/path/to/docker-selkies-egl-desktop/scripts/selkies_desktop_mcp_server.py",
        "--url",
        "http://localhost:8080",
        "--username",
        "ubuntu",
        "--password",
        "mypasswd",
        "--browser",
        "chromium",
        "--output-dir",
        "/tmp/selkies-mcp"
      ]
    }
  }
}
```

## Robust Deployment Notes

1. Launch desktop first, then start MCP server.
2. Call `wait_for_stream` before screenshot or action tools.
3. Keep one active browser viewer for Selkies at a time.
4. Use host networking (`docker-compose.jetson.yml`) for reliable WebRTC ICE on Jetson.
5. Rotate credentials if exposing beyond localhost.
