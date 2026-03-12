# GitHub Actions 构建并推送到 Docker Hub 教程

本教程将带你完成：每次推送到 GitHub，自动构建 Docker 镜像并推送到 Docker Hub。

---

## 一、准备工作

### 1.1 获取 Docker Hub 凭证

1. 登录 [Docker Hub](https://hub.docker.com)
2. 点击右上角头像 → **Account Settings**
3. 左侧菜单选择 **Security** → **New Access Token**
4. 填写：
   - **Description**：如 `github-actions`
   - **Access permissions**：选 **Read, Write, Delete**
5. 点击 **Generate**，**复制并妥善保存 Token**（只显示一次）

### 1.2 创建 GitHub 仓库

1. 登录 [GitHub](https://github.com)
2. 右上角 **+** → **New repository**
3. 填写：
   - **Repository name**：如 `jobsdb-autoapply`
   - **Public** 或 **Private** 自选
4. 点击 **Create repository**

---

## 二、添加 GitHub Secrets

1. 打开你的仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**，添加两个：

| Name | Value |
|------|-------|
| `DOCKERHUB_USERNAME` | 你的 Docker Hub 用户名 |
| `DOCKERHUB_TOKEN` | 上一步生成的 Access Token |

---

## 三、推送代码到 GitHub

### 3.1 初始化 Git（若尚未初始化）

在项目根目录打开终端，执行：

```bash
cd C:\Users\Administrator\Desktop\jobsdb_autoapply_py

git init
git add .
git commit -m "Initial commit"
```

### 3.2 关联远程仓库并推送

将 `你的用户名` 和 `你的仓库名` 替换为你的 GitHub 信息：

```bash
git remote add origin https://github.com/你的用户名/你的仓库名.git
git branch -M main
git push -u origin main
```

---

## 四、触发构建

### 方式一：自动触发

- 每次 `git push` 到 `main` 或 `master` 分支，都会自动构建并推送

### 方式二：手动触发

1. 打开仓库 → **Actions**
2. 左侧选择 **Build and Push to Docker Hub**
3. 点击 **Run workflow** → **Run workflow**
4. 等待运行完成（约 10–20 分钟，Playwright 镜像较大）

---

## 五、查看构建结果

1. 在 **Actions** 页面点击本次运行
2. 查看 `build-and-push` 任务是否显示绿色 ✓
3. 登录 [Docker Hub](https://hub.docker.com) → **Repositories**，应能看到 `jobsdb-autoapply`

---

## 六、VPS 上拉取并运行

构建成功后，在 VPS 上执行：

```bash
# 拉取镜像（替换为你的 Docker Hub 用户名）
docker pull 你的DockerHub用户名/jobsdb-autoapply:latest

# 创建数据目录
mkdir -p /opt/jobsdb_data

# 运行容器
docker run -d \
  --name jobsdb-autoapply \
  -p 8000:8000 \
  -v /opt/jobsdb_data:/app/data \
  -e JOBSDB_SECRET_KEY="你的随机密钥" \
  --restart unless-stopped \
  你的DockerHub用户名/jobsdb-autoapply:latest
```

---

## 七、更新版本流程

1. 本地修改代码
2. 提交并推送：
   ```bash
   git add .
   git commit -m "更新说明"
   git push
   ```
3. GitHub Actions 自动构建并推送新镜像
4. 在 VPS 上执行：
   ```bash
   docker pull 你的DockerHub用户名/jobsdb-autoapply:latest
   docker stop jobsdb-autoapply && docker rm jobsdb-autoapply
   # 再执行上面的 docker run
   ```

---

## 八、常见问题

| 问题 | 处理 |
|------|------|
| 构建失败：DOCKERHUB_USERNAME 相关 | 检查 Secrets 中 `DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN` 是否正确 |
| 构建超时 | 通常 15–25 分钟内完成，可重试 |
| 推送失败 401 | 确认 Token 权限为 Read+Write，且未过期 |
| 镜像名不符合预期 | 检查 workflow 中 `tags` 配置 |

---

## 九、文件结构确认

项目根目录应包含：

```
jobsdb_autoapply_py/
├── .github/
│   └── workflows/
│       └── docker-build-push.yml   ← 新增的 workflow
├── api/
├── web/
├── Dockerfile
├── requirements.txt
├── jobsdb_worker.py
└── ...
```

如果 `.github` 目录已创建，只需确保 `docker-build-push.yml` 存在并随 `git push` 一起推送即可。
