# JobsDB 投递控制台 - 本地运行

## 1. 安装依赖

```bash
# 后端
pip install -r api/requirements.txt
playwright install chromium

# 前端
cd web && npm install
```

## 2. 启动

**终端 1 - 后端**
```bash
python run_api.py
# 或: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

**终端 2 - 前端**
```bash
cd web && npm run dev
```

## 3. 访问

- 前端：<http://localhost:5173>
- 后端 API：<http://localhost:5173> 的请求会通过 Vite 代理到 `http://localhost:8000`

## 4. 数据目录

- 用户数据、登录状态、统计等保存在 `data/` 目录
- 数据库：`data/jobsdb_web.db`
