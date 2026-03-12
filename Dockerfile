# JobsDB 自动投递 - Docker 镜像
# 多阶段构建：前端构建 + Python 后端 + Playwright
FROM node:20-alpine AS frontend
WORKDIR /app/web
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright Chromium（镜像已包含，确保依赖齐全）
RUN playwright install chromium && playwright install-deps chromium

# Qt 无头模式（Docker 无显示器）
ENV QT_QPA_PLATFORM=offscreen
ENV DISPLAY=

# 复制项目代码
COPY api/ ./api/
COPY jobsdb_worker.py ./

# 复制前端构建产物
COPY --from=frontend /app/web/dist ./web/dist

# 数据目录（运行时通过 volume 挂载覆盖）
VOLUME ["/app/data"]

EXPOSE 8000

# 启动命令
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
