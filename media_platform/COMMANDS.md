# 爬虫运行命令

## 抖音 (dy)

```bash
# 创作者模式 —— 从数据库 douyin_aweme.sec_uid 自动获取待抓取创作者，无需传 creator_id
uv run main.py --platform dy --lt qrcode --type creator

# 搜索模式
uv run main.py --platform dy --lt qrcode --type search --keywords 猴子警长 --crawler_max_notes_count 100 --get_comment True --get_sub_comment True --max_comments_count_singlenotes 50

# 详情模式 —— 指定视频 URL 或 ID
uv run main.py --platform dy --lt qrcode --type detail --specified_id https://www.douyin.com/video/7309934001566194994
```

## 小红书 (xhs)

```bash
# 搜索模式
uv run main.py --platform xhs --lt qrcode --type search --keywords 旅行 --crawler_max_notes_count 50

# 创作者模式 —— 从数据库 xhs_note.user_id 自动获取待抓取创作者，无需传 creator_id
uv run main.py --platform xhs --lt qrcode --type creator

# 详情模式
uv run main.py --platform xhs --lt qrcode --type detail --specified_id https://www.xiaohongshu.com/explore/xxx
```

## 微博 (wb)

```bash
# 搜索模式
uv run main.py --platform wb --lt qrcode --type search --keywords 热点 --crawler_max_notes_count 50

# 创作者模式 —— 从数据库 weibo_note.user_id 自动获取待抓取创作者，无需传 creator_id
uv run main.py --platform wb --lt cookie --type creator

# 详情模式
uv run main.py --platform wb --lt cookie --type detail --specified_id 123456789
```

## B站 (bili)

```bash
# 搜索模式
uv run main.py --platform bili --lt cookie --type search --keywords 编程教程 --crawler_max_notes_count 50

# 创作者模式 —— 从数据库 bilibili_video.user_id 自动获取待抓取UP主，无需传 creator_id
uv run main.py --platform bili --lt cookie --type creator

# 详情模式
uv run main.py --platform bili --lt cookie --type detail --specified_id BV1xx411c7mD
```

## 快手 (ks)

```bash
# 搜索模式
uv run main.py --platform ks --lt qrcode --type search --keywords 美食 --crawler_max_notes_count 50

# 创作者模式
uv run main.py --platform ks --lt qrcode --type creator --creator_id https://www.kuaishou.com/profile/xxx
```

## 知乎 (zhihu)

```bash
# 搜索模式
uv run main.py --platform zhihu --lt cookie --type search --keywords 人工智能 --crawler_max_notes_count 30

# 详情模式
uv run main.py --platform zhihu --lt cookie --type detail --specified_id https://www.zhihu.com/question/xxx
```

## 贴吧 (tieba)

```bash
# 搜索模式
uv run main.py --platform tieba --lt cookie --type search --keywords 原神 --crawler_max_notes_count 50

# 创作者模式
uv run main.py --platform tieba --lt cookie --type creator --creator_id https://tieba.baidu.com/home/main?id=xxx
```

---

## 常用参数说明

| 参数 | 说明 | 可选值 |
|---|---|---|
| `--platform` | 平台 | `dy` `xhs` `wb` `bili` `ks` `zhihu` `tieba` |
| `--lt` | 登录方式 | `qrcode` `cookie` `phone` |
| `--type` | 爬取模式 | `search` `detail` `creator` |
| `--save_data_option` | 存储方式 | `db` `csv` `json` `jsonl` `sqlite` `mongodb` `excel` |
| `--keywords` | 搜索关键词，多个用逗号分隔 | |
| `--crawler_max_notes_count` | 最多抓取帖子/视频数 | 默认 `20` |
| `--get_comment` | 是否抓取一级评论 | `True` `False` |
| `--get_sub_comment` | 是否抓取二级评论 | `True` `False` |
| `--max_comments_count_singlenotes` | 单帖最多抓取评论数 | 默认 `20` |
| `--specified_id` | 详情模式指定 URL 或 ID，多个用逗号分隔 | |
| `--creator_id` | 创作者模式指定 URL 或 ID，多个用逗号分隔 | |
| `--headless` | 是否无头模式 | `True` `False` |
| `--cookies` | Cookie 登录时传入 cookie 字符串 | |

> **提示**：抖音、微博、小红书、B站的 `creator` 模式已改为从数据库自动读取待抓取 ID，无需传任何额外参数，直接运行即可。
