# 选物助手 · 淘宝风格 AI 导购

第一期本地 MVP。Python 3.11、FastAPI、原生 HTML/CSS/JavaScript、OpenAI 兼容 SDK 和本地 JSON。商品、优惠和订单均为虚构；项目不访问淘宝、支付或物流系统。

## 在 PyCharm 运行

打开 `taobao-ai-agent` 项目，确认解释器为项目中的 `.venv`（Python 3.11）。在 PyCharm 的 **Terminal** 中执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_local.py
```

已有依赖时直接运行第二条。默认连接 DeepSeek 官方接口并使用 `deepseek-flash`；若当前进程未配置 Key，启动器会提示你在终端隐藏输入。浏览器打开 `http://127.0.0.1:8000/`。接口文档在 `http://127.0.0.1:8000/docs`。按 `Ctrl+C` 停止服务。

### 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试无需模型账号，覆盖业务规则、HTTP 路由、SDK 工具消息协议、会话隔离和兜底。首次真实联调请在网页中发送“找 200 元以内的蓝牙耳机，按销量排序”，对照终端的 `tool=search_products` 日志及商品卡片。

- [运行与源码学习指南](docs/学习与运行指南.md)
- [验收清单与录屏脚本](docs/验收与录屏.md)
