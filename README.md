# 选物 3.0 · AI 购物助手

私有试点版本。LangChain 封装模型与工具，LangGraph 编排原生 Function Calling，RAG 查询本地「选物模拟资料」，LangSmith 追踪默认关闭。对话、收藏和来源快照存储在 SQLite。项目不访问真实淘宝、支付或物流系统。

## 在 PyCharm 运行

打开 `taobao-ai-agent` 项目，确认解释器为项目中的 `.venv`（Python 3.11）。在 PyCharm 的 **Terminal** 中执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m knowledge_index
.\.venv\Scripts\python.exe run_local.py
```

首次建索引会下载独立的中文嵌入模型，无需聊天 API Key。已有依赖和索引时直接运行启动器。默认调用 DeepSeek `deepseek-flash`；未配置 Key 时提示隐藏输入。浏览器打开 `http://127.0.0.1:8000/`。开发环境接口文档在 `http://127.0.0.1:8000/docs`。按 `Ctrl+C` 停止服务。

### 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m evaluate --mode offline
```

测试无需模型账号，覆盖业务规则、HTTP 路由、SDK 工具消息协议、会话隔离和兜底。首次真实联调请在网页中发送“找 200 元以内的蓝牙耳机，按销量排序”，对照终端的 `tool=search_products` 日志及商品卡片。

- [选物 3.0 运行与源码指南](docs/选物3.0运行与源码指南.md)
- [2.0 通用上线与运维手册](docs/生产部署与验收.md)
- [第一期运行与源码学习指南](docs/学习与运行指南.md)
- [第一期验收与录屏脚本](docs/验收与录屏.md)
