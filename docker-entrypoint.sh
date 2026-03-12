#!/bin/bash
set -e

# ENABLE_NOVNC=1 时启动虚拟显示 + noVNC，便于调试 JobsDB 登录
# 访问 http://VPS_IP:6080/vnc.html 查看浏览器画面
if [ "$ENABLE_NOVNC" = "1" ]; then
  export DISPLAY=:99
  Xvfb :99 -screen 0 1280x720x24 -ac &
  sleep 2
  x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &
  /opt/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 &
fi

exec uvicorn api.main:app --host 0.0.0.0 --port 8000
