#!/bin/bash

set -euo pipefail

export DISPLAY="${DISPLAY:-:20}"
RESULT=0

GLX_CMD=(glxinfo -B)
FIREFOX_CMD=(firefox --new-instance --no-remote "about:blank")
if command -v vglrun >/dev/null 2>&1; then
  # EGL desktop containers use VirtualGL for hardware OpenGL acceleration.
  GLX_CMD=(vglrun glxinfo -B)
  FIREFOX_CMD=(vglrun "${FIREFOX_CMD[@]}")
fi

echo "== OpenGL check =="
echo "OpenGL probe command: ${GLX_CMD[*]}"
if ! "${GLX_CMD[@]}" >/tmp/selkies-glxinfo.txt 2>/tmp/selkies-glxinfo.err; then
  echo "FAIL: OpenGL probe failed"
  cat /tmp/selkies-glxinfo.err
  RESULT=1
else
  GL_VENDOR="$(awk -F': ' '/OpenGL vendor string/ {print $2; exit}' /tmp/selkies-glxinfo.txt)"
  GL_RENDERER="$(awk -F': ' '/OpenGL renderer string/ {print $2; exit}' /tmp/selkies-glxinfo.txt)"
  echo "OpenGL vendor: ${GL_VENDOR:-unknown}"
  echo "OpenGL renderer: ${GL_RENDERER:-unknown}"
  if echo "${GL_RENDERER}" | grep -Eqi 'llvmpipe|software rasterizer'; then
    echo "FAIL: renderer indicates software rasterization"
    RESULT=1
  fi
  if ! echo "${GL_VENDOR} ${GL_RENDERER}" | grep -qi 'nvidia'; then
    echo "FAIL: renderer/vendor did not match NVIDIA"
    RESULT=1
  fi
fi

echo "== Vulkan check =="
if ! vulkaninfo --summary >/tmp/selkies-vulkaninfo.txt 2>/tmp/selkies-vulkaninfo.err; then
  echo "FAIL: vulkaninfo --summary failed"
  cat /tmp/selkies-vulkaninfo.err
  RESULT=1
else
  if ! grep -Eqi 'NVIDIA|Vulkan Instance Version' /tmp/selkies-vulkaninfo.txt; then
    echo "FAIL: vulkaninfo output did not show an NVIDIA-capable Vulkan stack"
    RESULT=1
  fi
  sed -n '1,80p' /tmp/selkies-vulkaninfo.txt
fi

echo "== Firefox GPU process library check =="
export MOZ_DISABLE_CONTENT_SANDBOX=1
export MOZ_DISABLE_RDD_SANDBOX=1
export MOZ_X11_EGL=1
export MOZ_WEBRENDER=1
echo "Firefox probe command: ${FIREFOX_CMD[*]}"
"${FIREFOX_CMD[@]}" >/tmp/selkies-firefox.log 2>&1 &
FIREFOX_PID=$!
sleep 12

FIREFOX_GPU_OK=1
for PID in "${FIREFOX_PID}" $(pgrep -f "firefox.*-contentproc" || true); do
  if [ -r "/proc/${PID}/maps" ] && grep -Eqs 'libEGL_nvidia|libGLX_nvidia|libnvidia-glcore' "/proc/${PID}/maps"; then
    FIREFOX_GPU_OK=0
    echo "Firefox GPU libraries detected in PID ${PID}"
    break
  fi
done

if [ "${FIREFOX_GPU_OK}" -ne 0 ]; then
  echo "FAIL: could not detect NVIDIA GL libraries in Firefox process maps"
  sed -n '1,160p' /tmp/selkies-firefox.log || true
  RESULT=1
fi

kill "${FIREFOX_PID}" >/dev/null 2>&1 || true
wait "${FIREFOX_PID}" >/dev/null 2>&1 || true

if [ "${RESULT}" -ne 0 ]; then
  echo "GPU/browser acceleration validation failed"
  exit 1
fi

echo "GPU/browser acceleration validation passed"
