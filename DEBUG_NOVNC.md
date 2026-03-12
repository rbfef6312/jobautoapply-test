# JobsDB 登录调试 - noVNC 可视化浏览器

当 VPS 上收不到 JobsDB 验证码时，可使用 noVNC 在浏览器中查看自动化操作的画面，便于排查。

## 1. 启用调试模式运行容器

```bash
docker stop jobsdb-autoapply
docker rm jobsdb-autoapply

docker run -d \
  --name jobsdb-autoapply \
  -p 8000:8000 \
  -p 6080:6080 \
  -v /opt/jobsdb_data:/app/data \
  -e JOBSDB_SECRET_KEY="WMT8ayp3jpj5hvz@pbe" \
  -e ENABLE_NOVNC=1 \
  -e JOBSDB_HEADED=1 \
  --restart unless-stopped \
  jj84024421/jobsdb-autoapply:latest
```

## 2. 查看浏览器画面

1. 打开 `http://你的VPS的IP:6080/vnc.html`
2. 点击页面上的 **Connect** 连接
3. 在网页上进入 JobsDB 登录页面，输入邮箱，点击发送验证码
4. 此时 noVNC 页面会显示 VPS 上 Chromium 的画面，可看到 JobsDB 页面的实际内容

## 3. 排查要点

- 是否出现验证码/人机验证（reCAPTCHA 等）
- 点击发送后页面提示什么
- 是否有错误信息或重定向

## 4. 调试完成后

如需恢复普通模式（不启用 noVNC，节省资源）：

```bash
docker stop jobsdb-autoapply
docker rm jobsdb-autoapply

docker run -d \
  --name jobsdb-autoapply \
  -p 8000:8000 \
  -v /opt/jobsdb_data:/app/data \
  -e JOBSDB_SECRET_KEY="WMT8ayp3jpj5hvz@pbe" \
  --restart unless-stopped \
  jj84024421/jobsdb-autoapply:latest
```
