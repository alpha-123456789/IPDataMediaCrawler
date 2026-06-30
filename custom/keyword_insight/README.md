# Keyword Insight 使用说明

基于社交平台（小红书、B站、微博等）抓取数据，对指定关键词进行话题、用户关注点、情感分布等多维度分析，并生成洞察报告。

## 运行方式

### 1. 模板模式（规则生成，无需 API Key）

```bash
uv run .\custom\keyword_insight\run.py 猴子警长
```

使用规则匹配生成结构化简报，输出话题分布、用户关注点、高频咨询等。

### 2. LLM 模式（AI 生成洞察报告）

```bash
uv run .\custom\keyword_insight\run.py 猴子警长 --llm
```

将分析数据交给 Claude 模型，生成 500-700 字的深度用户洞察报告。需要配置 API Key（见下方）。

### 3. LLM 模式 + 参考资料

```bash
uv run .\custom\keyword_insight\run.py 猴子警长 --llm --ref reference.txt
```

在 LLM 分析时额外注入参考文件内容（如竞品研究、行业报告），模型会将用户数据与参考资料交叉印证。

### 4. 分析全部关键词

```bash
uv run .\custom\keyword_insight\run.py
uv run .\custom\keyword_insight\run.py --llm
```

不传关键词时，依次对数据库中所有关键词运行分析。

## 可用关键词

关键词来源于数据库实际数据（通过 `KeywordRepository.get_keywords()` 查询），以下是 `config.py` 中预定义的 IP 系列及其关键词：

| IP 系列 | 代表关键词 |
|---------|-----------|
| 猴子警长系列 | 猴子警长、小鸡墩墩、兔子警长、弗兰熊、银狐… |
| 啦咘啦哆系列 | 啦咘啦哆、拉布拉多警长、杜兵警员… |
| 小鸡墩墩系列 | 小鸡墩墩、鸡一旦、卷毛猪、美食侦探… |
| 弹弹消防员系列 | 弹弹消防员、蓝星星、喵小丸… |
| 依娜恰恰系列 | 依娜恰恰、恰恰公主、依娜公主… |

如果传入的关键词不在数据库中，程序会提示 `关键词 'xxx' 不在数据库中` 并退出。

## LLM 模式环境变量

在 `.env` 文件中配置（复制 `.env.example` 修改）：

```env
# 必填：API Key（二选一）
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_AUTH_TOKEN=sk-ant-...

# 可选：自定义 API 地址（使用代理或内部端点时填写）
ANTHROPIC_BASE_URL=https://your-proxy.example.com

# 可选：指定模型（默认 claude-haiku-4-5-20251001）
ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

LLM 不可用时（Key 缺失或网络异常），自动降级到模板模式输出。

## 输出

报告通过 `ReportRepository.save()` 持久化，同时在终端打印 `done: <keyword>`。

- 模板模式报告标记为 `[模板生成]`
- LLM 模式报告标记为 `[AI 生成]`
