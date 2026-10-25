# WillPace v4

当前版本的启动、功能和指标定义见项目根目录的 `部署与启动说明.md`。

```powershell
python server_main.py
```

打开 http://localhost:3000。服务使用 SQLite 保存账号与报告，提供 HTTP API，不使用旧版 WebSocket 服务。

旧版本实现归档在 `legacy/server_main_v3.py`；旧 API 文档描述的是 v3，不适用于当前账号接口。当前 API 以 `service.py` 的路由和根目录说明为准。
