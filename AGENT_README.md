# Agent Desktop Validation Guide

This guide is for automation agents that need to launch the Jetson desktop container and verify a working browser-rendered GUI for computer-use workflows.

## 1. Launch the Desktop

Run from repo root:

```bash
./scripts/launch-jetson-desktop.sh
```

Behavior:

- Reuses existing `selkies-egl-desktop:jetson` image if present (no rebuild).
- Builds only when image is missing (or `FORCE_REBUILD=true` is set).
- Waits until the desktop startup is ready.
- Runs `scripts/post-launch-install.sh` as a post-setup hook.

Default web access:

- URL: `http://localhost:8080`
- Username: `ubuntu`
- Password: `mypasswd`

## 2. Optional Custom Software Install Hook

Edit:

```bash
scripts/post-launch-install.sh
```

Add package names to `CUSTOM_APT_PACKAGES` and re-run launch.  
The hook runs after desktop startup is complete.

## 3. Validate Browser GUI Render

Use the `codex` conda environment:

```bash
conda run -n codex python ./scripts/agent-gui-check.py --browser chromium
conda run -n codex python ./scripts/agent-gui-check.py --browser firefox
```

Success criteria:

- `"success": true`
- `"peerState": "connected"` in final state
- video dimensions are non-zero (for example `1920x1080`)

Artifacts:

- JSON status + screenshot in `/tmp/selkies-agent-gui/`

## 4. Validate In-Container GPU Acceleration

```bash
docker compose -f docker-compose.yml -f docker-compose.jetson.yml exec -T egl bash -lc /usr/local/bin/validate-acceleration
```

Expected:

- OpenGL vendor/renderer shows NVIDIA Orin/Tegra
- Vulkan summary lists NVIDIA device
- Firefox process maps include NVIDIA GL libraries

## 5. If Docker Requires Privileged Screen Session

If direct docker access is unavailable, run docker commands through a privileged `screen` session.

Discover available sessions:

```bash
screen -ls
```

Then send commands into the selected session:

```bash
screen -S <session-name> -p 0 -X stuff $'cd /path/to/repo\n./scripts/launch-jetson-desktop.sh\n'
```
