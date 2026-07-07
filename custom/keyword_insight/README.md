# Keyword Insight 使用说明

基于社交平台（小红书、B站、微博等）抓取数据，对指定关键词进行话题、用户关注点、情感分布等多维度分析，并生成洞察报告。

## 运行方式

### 单个关键词

```bash
# 模板模式（规则生成，无需 API Key）
uv run .\custom\keyword_insight\run.py 猴子警长

# LLM 模式（AI 生成洞察报告）
uv run .\custom\keyword_insight\run.py 猴子警长 --llm

# LLM + 参考资料
uv run .\custom\keyword_insight\run.py 猴子警长 --llm --ref reference.txt
```

### 批量生成报告（batch_report.py）

从 `crawler_keyword` 表中读取 `status=1` 的关键词，支持全部、指定、按分组三种模式：

```bash
# 列出所有可用关键词（status=1）
uv run custom/keyword_insight/batch_report.py --list

# 生成所有启用关键词的报告（已有报告的自动跳过）
uv run custom/keyword_insight/batch_report.py

# 强制重新生成所有报告（包括已有的）
uv run custom/keyword_insight/batch_report.py --force

# 只生成指定关键词
uv run custom/keyword_insight/batch_report.py 猴子警长 小鸡敦敦 弗兰熊

# 按 config.py 中的分组名生成
uv run custom/keyword_insight/batch_report.py --group 猴子警长系列

# 启用 LLM + 参考资料
uv run custom/keyword_insight/batch_report.py --llm --ref reference.txt

# LLM + 强制重新生成
uv run custom/keyword_insight/batch_report.py --llm --force
```

> **默认行为**：已存在报告的关键词会自动跳过，终端提示 `跳过已有报告：xxx`。加 `--force` / `-f` 可强制覆盖重新生成。

### 分析全部关键词（run.py）

```bash
uv run .\custom\keyword_insight\run.py
uv run .\custom\keyword_insight\run.py --llm
```

不传关键词时，依次对数据库中所有关键词运行分析。

## 可用关键词

关键词来源于 MySQL 数据库 `crawler_keyword` 表（`status=1`），以下是 `config.py` 中预定义的 IP 系列及其关键词：

| IP 系列 | 代表关键词 |
|---------|-----------|
| 猴子警长系列 | 猴子警长、小鸡墩墩、兔子警长、弗兰熊、银狐… |
| 啦咘啦哆系列 | 啦咘啦哆、拉布拉多警长、杜兵警员… |
| 小鸡墩墩系列 | 小鸡墩墩、鸡一旦、卷毛猪、美食侦探… |
| 弹弹消防员系列 | 弹弹消防员、蓝星星、喵小丸… |
| 依娜恰恰系列 | 依娜恰恰、恰恰公主、依娜公主… |

如果传入的关键词不在数据库中，程序会提示并跳过。

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
