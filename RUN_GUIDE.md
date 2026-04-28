# Tabbit2API 本地运行指南（Windows + WSL）

仓库地址：`https://github.com/miaoge2026/tabb2`

## 1) Windows 直接运行（源码）

在 PowerShell 中执行：

```powershell
cd D:\MyProjects\wo\tabb2
.\start.ps1
```

如果需要走 Clash 代理：

```powershell
cd D:\MyProjects\wo\tabb2
.\start.ps1 -UseProxy -ProxyUrl http://127.0.0.1:7890
```

可选参数：
- `-Port 9900`：修改服务端口，默认 `8800`

## 2) WSL 运行（源码）

在 WSL 中执行：

```bash
cd ~/apps/tabb2
chmod +x ./start.sh ./scripts/run_wsl.sh
./start.sh
```

如果需要走 Clash 代理（自动读取 WSL nameserver 作为 Windows 主机地址）：

```bash
cd ~/apps/tabb2
chmod +x ./start.sh ./scripts/run_wsl.sh
./start.sh --proxy
```

可选环境变量：
- `APP_PORT=9900 ./start.sh`
- `PROXY_PORT=7890 ./start.sh --proxy`

## 3) 运行成功后验证

浏览器访问：
- `http://localhost:8800/admin`

接口验证：

```bash
curl http://localhost:8800/v1/models
```

管理员登录接口（默认密码 `admin`）：

```bash
curl -X POST http://localhost:8800/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password":"admin"}'
```

## 4) 说明

- Windows 与 WSL 只需要选一种方式运行即可，不建议同时占用同一端口。
- 若端口冲突，请用 `-Port`（Windows）或 `APP_PORT`（WSL）改端口。
