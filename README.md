# 选物

选物是一个购物助手练习项目。可以先问「200 元以内有哪些蓝牙耳机？」，再接着问「第一款有蓝色吗？」。也可以查优惠券和订单、收藏商品。查询选购知识时，回答下方会显示查到的资料片段。

商品、订单和资料都是项目里的模拟数据。后端用 FastAPI 和 LangGraph，前端用原生 HTML、CSS 和 JavaScript，对话和收藏保存在 SQLite。

## 本地运行

用 Python 3.11 创建并激活虚拟环境，在项目目录运行：

```powershell
python -m pip install -r requirements.txt
python -m knowledge_index
python run_local.py
```

第一次建索引会下载中文嵌入模型。启动后按提示输入 DeepSeek API Key，再打开 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)。

配置和代码结构见[运行与源码指南](docs/选物3.0运行与源码指南.md)。
