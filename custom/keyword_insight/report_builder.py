import json
import re

from custom.keyword_insight.config import CONCERN_CLUSTER_IMPACT


class ReportBuilder:

    @staticmethod
    def build(keyword, notes, comments, creators,
              topics, roles, concerns, questions, sentiment,
              engagement, geography, creator_analysis, tags, time_trend,
              use_llm=False, reference_content="", creator_count=None):

        if use_llm:
            return ReportBuilder._build_llm_report(
                keyword, notes, comments, concerns, topics, sentiment,
                engagement, questions, reference_content, creator_count
            )

        # ── 规则模式 ────────────────────────────────────────────────────────
        lines = []
        lines.append(f"关键词分析简报：{keyword}")
        lines.append("[模板生成]")

        # 【数据概览】
        lines.append("\n【数据概览】")
        total_likes = engagement.get("total_likes", 0)
        c_count = creator_count if creator_count is not None else len(creators)
        lines.append(
            f"笔记 {len(notes)} 篇 | 评论 {len(comments)} 条 | 创作者 {c_count} 位 | 累计点赞 {total_likes}"
        )

        # 【情感速览】
        lines.append("\n【情感速览】")
        dist = sentiment.get("distribution", {})
        pos = dist.get("positive", 0)
        neg = dist.get("negative", 0)
        neu = dist.get("neutral", 0)
        if neu >= 70:
            if pos > neg:
                lines.append(f"整体偏正面（正面信号 {pos}% / 负面信号 {neg}%），多数为中性陈述")
            elif neg > pos:
                lines.append(f"整体偏负面（负面信号 {neg}% / 正面信号 {pos}%），多数为中性陈述")
            else:
                lines.append(f"情感信号较弱（正面 {pos}% / 负面 {neg}%），讨论以中性陈述为主")
        else:
            lines.append(f"正面 {pos}% | 中性 {neu}% | 负面 {neg}%")

        # 【核心讨论】
        lines.append("\n【核心讨论】")
        if topics:
            parts = [f"{x['topic']}({x['percent']}%)" for x in topics[:3]]
            lines.append(" | ".join(parts))
        else:
            lines.append("无明显话题聚集")

        # 【用户关注点】
        lines += ReportBuilder._build_concerns_rule(concerns)

        # 【高频咨询】
        lines.append("\n【高频咨询】")
        top_qs = questions[:5]
        if top_qs:
            for i, q in enumerate(top_qs, 1):
                clean_text = re.sub(r'#.*?\[话题\]#', '', q['text']).strip()
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                summary = (clean_text[:50] + "...") if len(clean_text) > 50 else clean_text
                summary = summary.replace("\n", "").replace("\r", "")
                cluster_info = f"相似{q.get('cluster_size', 1)}条" if q.get('cluster_size', 1) >= 2 else "热门帖"
                lines.append(f"{i}. {summary} (赞{q.get('like_count', 0)} 评{q.get('comment_count', 0)} {cluster_info})")

                answers = q.get('answers', [])
                if answers:
                    comment_texts = []
                    for ans in answers[:2]:
                        clean_ans = re.sub(r'#.*?\[话题\]#', '', ans['text']).strip()
                        clean_ans = re.sub(r'\s+', ' ', clean_ans).strip()
                        if clean_ans.startswith("?"):
                            clean_ans = clean_ans[1:].strip()
                        comment_texts.append(clean_ans)
                    if comment_texts:
                        numbered = [f"{j+1}. {txt}" for j, txt in enumerate(comment_texts)]
                        combined = re.sub(r'[\r\n\t]', ' ', "；".join(numbered)).strip()
                        if len(combined) > 50:
                            combined = combined[:50] + "..."
                        lines.append(f"   评论: {combined}")
                    else:
                        lines.append("   暂无相关评论")
                else:
                    lines.append("   暂无相关评论")
        else:
            lines.append("暂无明显咨询内容")

        return "\n".join(lines)

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

        try:
            import anthropic, os

            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
            base_url = os.environ.get("ANTHROPIC_BASE_URL")
            model = (
                os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
                or os.environ.get("ANTHROPIC_MODEL")
                or "claude-haiku-4-5-20251001"
            )
            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = anthropic.Anthropic(**client_kwargs)

            resp = client.messages.create(
                model=model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            report_text = next((b.text for b in resp.content if hasattr(b, "text")), "").strip()
            return f"关键词洞察报告：{keyword}\n[AI 生成]\n\n{report_text}"

        except Exception as e:
            print(f"[LLM] 报告生成失败：{e}，降级到规则模式")
            # 降级：用规则模式重新生成
            lines = [f"关键词分析简报：{keyword}（LLM 不可用，已降级）"]
            lines += ReportBuilder._build_concerns_rule(concerns)
            return "\n".join(lines)

    # ── 规则版：简洁，一行一个关注点 ────────────────────────────────────────

    @staticmethod
    def _build_concerns_rule(concerns):
        lines = ["\n【用户关注点】"]
        top_concerns = [c for c in concerns if c.get("count", 0) > 0][:5]
        if not top_concerns:
            lines.append("无明显关注点")
            return lines

        for item in top_concerns:
            concern_name = item["concern"]
            count = item.get("count", 0)
            subclusters = item.get("subclusters", [])

            sig = [sc for sc in subclusters[:4] if sc.get("percent", 0) >= 5][:2]
            parts = []
            for sc in sig:
                desc = sc.get("desc", "")
                pct = sc.get("percent", 0)
                tag = f"{sc['name']}({pct}%)"
                parts.append(f"{tag}{desc}" if desc else tag)

            line = f"• {concern_name}({count}条)"
            if parts:
                line += "：" + "；".join(parts)
            lines.append(line)

        return lines

    # ── LLM 版：一次调用生成全部洞察，格式由 LLM 自由决定 ─────────────────

    @staticmethod
    def _build_concerns_llm(concerns, keyword="", reference_content=""):
        lines = ["\n【核心用户反馈】"]
        top_concerns = [c for c in concerns if c.get("count", 0) > 0][:5]
        if not top_concerns:
            lines.append("无明显关注点")
            return lines

        result = ReportBuilder._call_full_llm(top_concerns, keyword, reference_content)
        if result:
            lines.append(result)
        else:
            # LLM 失败时降级到规则版
            for idx, item in enumerate(top_concerns, 1):
                concern_name = item["concern"]
                count = item.get("count", 0)
                subclusters = item.get("subclusters", [])
                lines.append(f"\n{idx}. {concern_name}（{count}条）")
                if subclusters:
                    top_sc = subclusters[0]
                    lines.append(f"{top_sc['name']}({top_sc['percent']}%)：{top_sc.get('desc', '')}")

        return lines

    @staticmethod
    def _call_full_llm(top_concerns, keyword, reference_content):
        """一次 LLM 调用生成完整用户洞察报告，格式不限，失败返回 None。"""
        try:
            import anthropic, os

            api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
            base_url = os.environ.get("ANTHROPIC_BASE_URL")
            model = (
                os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
                or os.environ.get("ANTHROPIC_MODEL")
                or "claude-haiku-4-5-20251001"
            )

            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = anthropic.Anthropic(**client_kwargs)

            # 构建用户数据块
            concerns_block = ""
            for item in top_concerns:
                name = item["concern"]
                count = item.get("count", 0)
                samples = [t for t in item.get("raw_samples", []) if t][:15]
                sample_text = "\n".join(f"  · {t}" for t in samples)
                concerns_block += f"\n▌{name}（{count}条）\n{sample_text}\n"

            ref_section = (
                f"以下是相关领域的背景参考资料，请结合参考资料对用户数据进行分析：\n\n{reference_content}\n\n---\n\n"
                if reference_content else ""
            )

            prompt = f"""你是儿童内容行业的资深用户研究专家，正在分析来自多个社交平台（小红书、B站、抖音、微博等）的真实用户反馈数据。

{ref_section}以下是关键词「{keyword}」的用户反馈分类数据（每类附有原始评论样本）：
{concerns_block}

请基于以上数据{"，结合背景参考资料" if reference_content else ""}，生成一份深度用户洞察报告。

要求：
- 格式自由，根据内容需要自行组织，不要有模板感
- 将用户真实反馈与{"参考资料中的研究结论" if reference_content else "各维度数据"}相互印证
- 点出值得关注的用户心理模式、潜在风险点
- 提供针对该内容IP的具体产品或运营建议
- 语言专业、简洁，500～800字"""

            resp = client.messages.create(
                model=model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )

            return next((b.text for b in resp.content if hasattr(b, "text")), "").strip()

        except Exception as e:
            print(f"[LLM] 报告生成失败：{e}")
            return None
