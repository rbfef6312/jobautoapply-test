# JobsDB 自动投递 - Docker 部署指南（1Panel）

## 一、一键部署步骤

### 1. 上传代码到 VPS

将整个项目上传到 VPS，例如 `/opt/jobsdb_autoapply_py/`

### 2. 构建镜像

```bash
cd /opt/jobsdb_autoapply_py
docker build -t jobsdb-autoapply:latest .
```

### 3. 创建数据目录（首次）

```bash
mkdir -p /opt/jobsdb_data
```

### 4. 一键运行（docker run）

```bash
docker run -d \
  --name jobsdb-autoapply \
  -p 8000:8000 \
  -v /opt/jobsdb_data:/app/data \
  -e JOBSDB_SECRET_KEY="请改为随机字符串" \
  --restart unless-stopped \
  jobsdb-autoapply:latest
```

**参数说明：**
- `-p 8000:8000`：宿主机 8000 端口映射
- `-v /opt/jobsdb_data:/app/data`：数据持久化（账号、登录态、数据库、日志）
- `-e JOBSDB_SECRET_KEY`：生产环境务必设置随机密钥
- `-e JOBSDB_PROXY`（可选）：住宅代理，用于 JobsDB 流量，格式 `socks5://host:port:user:pass` 或 `socks5://user:pass@host:port`

### 5. 1Panel 反代配置

1. 打开 1Panel → **网站** → **创建网站**
2. 选择 **反向代理**
3. 填写：
   - **域名**：如 `jobsdb.yourdomain.com`
   - **代理地址**：`http://127.0.0.1:8000`
   - 开启 **WebSocket**（若需要）
4. 如用 HTTPS，在 1Panel 申请 SSL 证书
5. 保存后即可通过域名访问

---

## 二、首次使用

1. 浏览器访问 `https://jobsdb.yourdomain.com`
2. 注册账号
3. 进入「JobsDB 登录」完成 JobsDB 验证码登录
4. 配置自动投递或手动投递

---

## 三、更新版本

```bash
cd /opt/jobsdb_autoapply_py
git pull   # 或重新上传新代码
docker build -t jobsdb-autoapply:latest .
docker stop jobsdb-autoapply
docker rm jobsdb-autoapply
# 使用同样的 docker run 命令重新创建（注意保留 -v 挂载路径）
# 如需香港住宅代理，加 -e JOBSDB_PROXY="socks5://host:port:user:pass"
docker run -d \
  --name jobsdb-autoapply \
  -p 8000:8000 \
  -v /opt/jobsdb_data:/app/data \
  -e JOBSDB_SECRET_KEY="你的密钥" \
  --restart unless-stopped \
  jobsdb-autoapply:latest
```

数据在 `/opt/jobsdb_data`，更新镜像不会丢失。

---

## 四、常用命令

```bash
# 查看日志
docker logs -f jobsdb-autoapply

# 停止
docker stop jobsdb-autoapply

# 启动
docker start jobsdb-autoapply
```
