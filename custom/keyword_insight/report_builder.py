import os


AI_FAILURE_MESSAGE = "AI生成失败，请稍后重试"
DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_LLM_TIMEOUT_SECONDS = 110


def _env_float(name, default):
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return float(default)
    return value if value > 0 else float(default)


def _error_summary(exc):
    """保留接口错误的类型和状态码，避免失败时只剩下笼统提示。"""
    status_code = getattr(exc, "status_code", None)
    detail = str(exc).strip() or repr(exc)
    prefix = f"{type(exc).__name__}"
    if status_code is not None:
        prefix += f" HTTP {status_code}"
    return f"{prefix}: {detail}"


def configured_llm_models():
    """返回按优先级排序、去重后的报告生成模型列表。"""
    models = [
        os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
        or os.environ.get("ANTHROPIC_MODEL")
        or DEFAULT_LLM_MODEL,
        os.environ.get("ANTHROPIC_FALLBACK_MODEL_1"),
        os.environ.get("ANTHROPIC_FALLBACK_MODEL_2"),
    ]
    return list(dict.fromkeys(model.strip() for model in models if model and model.strip()))


def generate_llm_report(prompt, max_tokens):
    """依次尝试配置的报告模型，任一模型成功时立即返回生成内容。"""
    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get(
            "ANTHROPIC_API_KEY", ""
        )
        client_kwargs = {"api_key": api_key}
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        if base_url:
            client_kwargs["base_url"] = base_url
        client_kwargs["timeout"] = _env_float(
            "ANTHROPIC_TIMEOUT_SECONDS",
            DEFAULT_LLM_TIMEOUT_SECONDS,
        )
        client = anthropic.Anthropic(**client_kwargs)
    except Exception as exc:
        print(f"[LLM] 初始化客户端失败：{exc}", flush=True)
        return None

    models = configured_llm_models()
    for index, model in enumerate(models, start=1):
        try:
            print(f"[LLM] 正在请求模型（{index}/{len(models)}）：{model}", flush=True)
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            report_text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "",
            ).strip()
            if not report_text:
                raise RuntimeError("LLM 未返回报告内容")
            print(f"[LLM] 模型生成成功：{model}", flush=True)
            return report_text
        except Exception as exc:
            print(f"[LLM] 模型 {model} 生成失败：{_error_summary(exc)}", flush=True)

    print("[LLM] 所有配置模型均生成失败", flush=True)
    return None


class ReportBuilder:

    @staticmethod
    def build(keyword, notes, comments, creators,
              topics, roles, concerns, questions, sentiment,
              engagement, geography, creator_analysis, tags, time_trend,
              use_llm=True, reference_content="", creator_count=None):

        return ReportBuilder._build_llm_report(
            keyword, notes, comments, concerns, topics, sentiment,
            engagement, questions, reference_content, creator_count
        )

    @staticmethod
    def _build_llm_report(keyword, notes, comments, concerns, topics, sentiment,
                          engagement, questions, reference_content, creator_count=None):
        """LLM 模式：把所有数据一次性给 LLM，生成一份完整洞察报告。"""
        top_concerns = [c for c in concerns if c.get("count", 0) > 0][:5]

        # 组装数据摘要供 LLM 参考
        dist = sentiment.get("distribution", {})
        sentiment_summary = f"正面 {dist.get('positive', 0)}% / 中性 {dist.get('neutral', 0)}% / 负面 {dist.get('negative', 0)}%"

        topic_summary = "、".join(f"{x['topic']}({x['percent']}%)" for x in topics[:5]) if topics else "无"

        concerns_block = ""
        for item in top_concerns:
            name = item["concern"]
            count = item.get("count", 0)
            raw = [t for t in item.get("raw_samples", []) if t][:30]
            samples = [t[:200] for t in raw]
            sample_text = "\n".join(f"  · {t}" for t in samples)
            concerns_block += f"\n▌{name}（{count}条）\n{sample_text}\n"

        c_count = creator_count if creator_count is not None else 0
        stats = (
            f"数据规模：笔记 {len(notes)} 篇，评论 {len(comments)} 条，创作者 {c_count} 位，"
            f"累计点赞 {engagement.get('total_likes', 0)}\n"
            f"情感分布：{sentiment_summary}\n"
            f"核心话题：{topic_summary}"
        )

        ref_section = (
            f"以下是相关领域的背景参考资料：\n\n{reference_content}\n\n---\n\n"
            if reference_content else ""
        )

        prompt = f"""你是儿童内容行业的资深用户研究专家，正在分析来自多个社交平台（小红书、B站、抖音、微博等）的真实用户反馈数据。

{ref_section}关键词：「{keyword}」

数据概况：
{stats}

用户关注点分类与原始评论样本：
{concerns_block}

请{"结合背景参考资料，" if reference_content else ""}基于以上数据生成一份完整的用户洞察报告。

要求：
- 直接输出报告正文，不要有"以下是报告"之类的前缀
- 格式自由，根据内容需要自行组织，不要有模板感
- 将用户真实反馈{"与参考资料研究结论" if reference_content else ""}相互印证，指出规律与风险
- 给出针对该 IP 的具体产品或运营建议
- 语言专业、简洁，字数严格控制在500～700字之间，不得超出"""

        report_text = generate_llm_report(prompt, max_tokens=1000)
        if report_text:
            return f"关键词洞察报告：{keyword}\n[AI 生成]\n\n{report_text}"
        return AI_FAILURE_MESSAGE
