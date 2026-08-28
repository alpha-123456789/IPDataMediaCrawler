# Keyword Insight 使用说明

基于社交平台（小红书、B站、微博等）抓取数据，对指定关键词进行话题、用户关注点、情感分布等多维度分析，并生成洞察报告。

## 运行方式

### 单个关键词

```bash
# AI 生成洞察报告
uv run .\custom\keyword_insight\run.py 猴子警长

# AI + 参考资料
uv run .\custom\keyword_insight\run.py 猴子警长 --ref reference.txt
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

# AI + 参考资料
uv run custom/keyword_insight/batch_report.py --ref reference.txt

# 强制重新生成
uv run custom/keyword_insight/batch_report.py --force
```

> **默认行为**：已存在报告的关键词会自动跳过，终端提示 `跳过已有报告：xxx`。加 `--force` / `-f` 可强制覆盖重新生成。

### 分析全部关键词（run.py）

```bash
uv run .\custom\keyword_insight\run.py
```

不传关键词时，依次对数据库中所有关键词运行分析。

### 自定义筛选报告（custom_report.py）

按**帖子发布日期**加载源数据，并根据可选的帖子 ID 集合进一步筛选。`--report-name`、`--prompt`、`--start-date`、`--end-date` 和 `--platform` 为必传；不传 `--post-ids` 时使用该平台在日期范围内的全部帖子。

```bash
uv run -m custom.keyword_insight.custom_report `
  --report-name "2026年7月国学小红书报告" `
  --prompt "分析用户对产品品质和购买意愿的反馈，并给出建议" `
  --start-date 2026-07-01 `
  --end-date 2026-07-31 `
  --platform xhs

# 限定特定帖子；可混用空格和逗号
uv run -m custom.keyword_insight.custom_report `
  --report-name "2026年7月争议点报告" `
  --prompt "总结争议点" `
  --start-date 2026-07-01 `
  --end-date 2026-07-31 `
  --platform dy `
  --post-ids 987654,123456
```

`--end-date` 包含当天。`--platform` 支持 `xhs`、`bili`、`dy`、`ks`、`wb`、`tieba`、`zhihu`；`--post-ids` 仅传当前平台的原始 ID。为兼容已有调用，`--pompt` 也可作为 `--prompt` 使用。

### 本地任务执行器

后台点击“生成报告”只会向 `keyword_report_task` 写入任务。本地运行项目根目录的 `start_keyword_report_runner.bat` 后，执行器会每 3 秒领取一条待执行任务，运行 `custom_report`，并把最终报告写入 `keyword_report`。

执行器会持续运行，关闭窗口或按 `Ctrl+C` 即可停止。任务失败时会更新 `keyword_report_task.status=3` 和 `error_message`；没有查到符合条件的帖子同样会标记为失败，不会产生空报告。

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

# 可选：指定主模型（默认 claude-haiku-4-5-20251001）
ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-haiku-4-5-20251001

# 可选：主模型失败时按顺序尝试两个备用模型
ANTHROPIC_FALLBACK_MODEL_1=your-second-model
ANTHROPIC_FALLBACK_MODEL_2=your-third-model

# 兼容旧配置：仅在未设置 ANTHROPIC_DEFAULT_HAIKU_MODEL 时作为主模型使用
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

所有报告都由 AI 生成，不再提供模板模式。系统会依次尝试主模型和两个备用模型；全部失败或均未返回内容时，报告内容固定为 `AI生成失败，请稍后重试`。

## 输出

自定义报告通过 `CustomReportRepository.save()` 写入 `keyword_report`，同名报告会更新既有结果。

- AI 报告标记为 `[AI 生成]`
- AI 生成失败时保存提示 `AI生成失败，请稍后重试`
