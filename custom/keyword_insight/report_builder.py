class ReportBuilder:

    @staticmethod
    def build(keyword, notes, comments, creators,
              topics, roles, concerns, questions, sentiment,
              engagement, geography, creator_analysis, tags, time_trend):

        lines = []

        lines.append(f"关键词分析简报：{keyword}")

        # 【数据概览】（一行汇总）
        lines.append("\n【数据概览】")
        note_count = len(notes)
        comment_count = len(comments)
        creator_count = len(creators)
        total_likes = engagement.get("total_likes", 0)
        lines.append(
            f"笔记 {note_count} 篇 | 评论 {comment_count} 条 | 创作者 {creator_count} 位 | 累计点赞 {total_likes}"
        )

        # 【情感速览】（突出有信号极性）
        lines.append("\n【情感速览】")
        dist = sentiment.get("distribution", {})
        pos = dist.get("positive", 0)
        neg = dist.get("negative", 0)
        neu = dist.get("neutral", 0)
        # 中性过高（说明词典对短文本命中弱）时，只突出有效信号
        if neu >= 70:
            if pos > neg:
                lines.append(f"整体偏正面（正面信号 {pos}% / 负面信号 {neg}%），多数为中性陈述")
            elif neg > pos:
                lines.append(f"整体偏负面（负面信号 {neg}% / 正面信号 {pos}%），多数为中性陈述")
            else:
                lines.append(f"情感信号较弱（正面 {pos}% / 负面 {neg}%），讨论以中性陈述为主")
        else:
            lines.append(f"正面 {pos}% | 中性 {neu}% | 负面 {neg}%")

        # 【核心讨论】（TOP3话题）
        lines.append("\n【核心讨论】")
        if topics:
            parts = [f"{x['topic']}({x['percent']}%)" for x in topics[:3]]
            lines.append(" | ".join(parts))
        else:
            lines.append("无明显话题聚集")

        # 【用户关注点】（核心，讲清具体讨论什么，控制字数）
        lines.append("\n【用户关注点】")
        top_concerns = [c for c in concerns if c.get("count", 0) > 0][:3]
        if top_concerns:
            for item in top_concerns:
                concern_name = item["concern"]
                count = item.get("count", 0)
                subclusters = item.get("subclusters", [])
                # 标题行：关注类别 + 条数 + TOP1子簇占比
                head = f"• {concern_name}({count}条)"
                if subclusters:
                    head += f"：{subclusters[0]['name']}({subclusters[0]['percent']}%)"
                lines.append(head)
                # 具体讨论内容：用 TOP2 子簇的描述拼成一句
                descs = [
                    sc.get("desc") for sc in subclusters[:2]
                    if sc.get("desc")
                ]
                if descs:
                    lines.append("  " + "；".join(descs) + "。")
        else:
            lines.append("无明显关注点")

        # 【高频咨询】（来自帖子聚类 + 高赞回答）
        lines.append("\n【高频咨询】")
        top_qs = questions[:5]  # 已按热度/聚类排序
        if top_qs:
            for i, q in enumerate(top_qs, 1):
                # 帖子内容（清理话题标签但保留表情）
                import re
                clean_text = re.sub(r'#.*?\[话题\]#', '', q['text']).strip()
                # 保留表情符号[xxx]，只清理多余空白
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                # 提取核心意思（截取前50字）
                if len(clean_text) > 50:
                    summary = clean_text[:50] + "..."
                else:
                    summary = clean_text
                # 生成更精炼的摘要
                summary = summary.replace("\n", "").replace("\r", "")
                line = f"{i}. {summary}"
                cluster_info = f"相似{q.get('cluster_size', 1)}条" if q.get('cluster_size', 1) >= 2 else "热门帖"
                like_count = q.get('like_count', 0)
                comment_count = q.get('comment_count', 0)
                line += f" (赞{like_count} 评{comment_count} {cluster_info})"
                lines.append(line)

                # 展示高赞回答
                answers = q.get('answers', [])
                if answers:
                    # 清理并总结合并评论
                    comment_texts = []
                    for ans in answers[:2]:  # 限制回答数
                        # 清理回答中的话题标签，保留表情
                        clean_ans = re.sub(r'#.*?\[话题\]#', '', ans['text']).strip()
                        clean_ans = re.sub(r'\s+', ' ', clean_ans).strip()
                        # 移除开头的"?"
                        if clean_ans.startswith("?"):
                            clean_ans = clean_ans[1:].strip()
                        comment_texts.append(clean_ans)

                    # 对评论进行总结归纳，生成一句话总结
                    if comment_texts:
                        # 每个评论前加序号
                        numbered = [f"{j+1}. {txt}" for j, txt in enumerate(comment_texts)]
                        combined = "；".join(numbered)
                        # 删除换行符，限制字数
                        combined = re.sub(r'[\r\n\t]', ' ', combined).strip()
                        if len(combined) > 50:
                            combined = combined[:50] + "..."
                        # 生成最终评论摘要
                        ans_line = f"   评论: {combined}"
                        lines.append(ans_line)
                    else:
                        lines.append("   暂无相关评论")
                else:
                    lines.append("   暂无相关评论")
        else:
            lines.append("暂无明显咨询内容")

        return "\n".join(lines)
