# AI 错误清单

作业要求至少 3 条，每条包含四要素：AI 给了什么、错在哪、怎么发现、最终怎么修。下面 6 条是本次开发中真实发生的记录。

| # | AI 给了什么（代码/建议） | 错在哪 | 怎么发现 | 最终怎么修正 |
| --- | --- | --- | --- | --- |
| 1 | Gradio 界面代码里写了 `gr.Chatbot(type="messages", show_copy_button=True)` | 用的是 Gradio 5 的旧参数；本机实际安装 Gradio 6.30，`Chatbot` 已移除 `type`，复制按钮改成了 `buttons` | 构造界面的冒烟测试报 `TypeError: Chatbot.__init__() got an unexpected keyword argument 'type'` | 用 `inspect.signature(gr.Chatbot.__init__)` 查真实参数，改成 `gr.Chatbot(height=520, label="对话", buttons=["copy"])` |
| 2 | 单元测试断言 `query_coverage("莫干山 雪山") == 0.5` | 忽略 jieba 搜索模式会把“莫干山”再切成“莫干”“干山”“山”等子词，实际覆盖率 0.667，测试假设本身错了 | `pytest -q` 断言失败，打印 0.6666666666666666 | 改成“部分命中，0 < coverage < 1”，补完全无关为 0 的断言 |
| 3 | 初版把向量拒答阈值拍脑袋设为 0.35，并声称“相关 >0.52、无关 <0.30” | 阈值和描述都没有实测依据；校准后无关问题 0.509，相关问题下限 0.441，两组分数重叠 | 8 个相关问题 + 8 个无关问题逐条打印 Top-1 分数 | 阈值改 0.40，只做粗筛；语义陷阱交给生成阶段提示词 |
| 4 | 引用解析正则只写 `\[(\d+)\]` | 模型实际输出中文括号 `【1】`，导致 citations 列为空 | pilot 回答有 `【1】`，CSV 的 citations 列却为空 | 正则同时匹配 `[] 【】 ［］ 〔〕`，补单测 |
| 5 | 直接用 fastembed 默认临时缓存目录下载模型 | 沙箱/临时目录权限导致模型反复下载失败，`ingest` 建不起向量索引 | 运行 `ingest` 报 `PermissionError`，随后 `Could not load model ... from any source` | 支持 `EMBEDDING_MODEL_PATH` 离线 ONNX 目录，缓存改到工作区 `.cache/`；保留默认下载作为回退 |
| 6 | 用 `for chunk in stream: chunk.choices[0].delta.content` 直接取流式内容 | 部分 OpenAI 兼容接口会先返回 `choices=[]` 的 usage/心跳块，触发 `IndexError: list index out of range` | 流式冒烟测试直接抛 `IndexError` | 跳过空 `choices`，只拼接非空 `delta.content`；同时把首 token 时间戳记在第一个内容块上 |

## 记录建议

- 保留原始报错信息和复现命令，写清楚是哪个文件、哪一行；
- “怎么发现”尽量写可复现的动作，例如运行了哪条命令、对照了哪份文档；
- “怎么修正”要写最终生效的改法，而不是“让 AI 再改一次”；
- 同一个问题被 AI 连续改错两次也值得记录，它能体现判断过程。
