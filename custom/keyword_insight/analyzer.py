import re
from difflib import SequenceMatcher
from collections import Counter
from datetime import datetime
from custom.keyword_insight.config import (
    TOPIC_RULES, CONCERN_RULES, QUESTION_WORDS,
    IP_KEYWORDS, GENERIC_ROLE_KEYWORDS,
    CONCERN_CLUSTER_RULES, CONCERN_CLUSTER_DESC,
    ENGAGEMENT_LEVEL_RULES, CREATOR_TYPE_RULES
)


def safe_int(val):
    """安全地将值转换为整数，处理字符串类型和空值"""
    try:
        return int(val) if val else 0
    except (ValueError, TypeError):
        return 0


class Analyzer:

    # ---------------- 文本相似度工具 ----------------
    @staticmethod
    def _extract_keywords(text):
        """提取中文关键词：保留长度>=2的连续中文字符/数字/字母"""
        tokens = re.findall(r'[一-龥]{2,}', str(text))
        # 加入咨询意图相关的数字短语
        number_phrases = re.findall(r'\d+[岁年级]', str(text))
        return set(tokens + number_phrases)

    def _similarity(self, text1, text2):
        """计算两段文本的相似度（Jaccard + 序列相似度混合）"""
        kw1 = self._extract_keywords(text1)
        kw2 = self._extract_keywords(text2)
        if not kw1 or not kw2:
            return 0.0
        jac_sim = len(kw1 & kw2) / len(kw1 | kw2)
        seq_sim = SequenceMatcher(None, text1, text2).ratio()
        # 关键词相似度占70%，序列相似度占30%
        return round(jac_sim * 0.7 + seq_sim * 0.3, 3)

    # ---------------- 原有分析维度 ----------------
    def analyze_topics(self, texts):
        """分析话题分布，返回命中关键词和代表性文本"""
        counter = Counter()
        kw_counter = {}  # topic -> Counter of keyword hits
        samples = {}     # topic -> list of sample texts

        for topic in TOPIC_RULES:
            kw_counter[topic] = Counter()
            samples[topic] = []

        for t in texts:
            for topic, kws in TOPIC_RULES.items():
                hits = [k for k in kws if k in t]
                if hits:
                    counter[topic] += 1
                    kw_counter[topic].update(hits)
                    if len(samples[topic]) < 3:
                        samples[topic].append(t[:100])

        total = sum(counter.values()) or 1

        return [
            {
                "topic": k,
                "count": v,
                "percent": round(v * 100 / total, 2),
                "matched_keywords": [kw for kw, _ in kw_counter[k].most_common(3)],
                "top_keywords": kw_counter[k].most_common(5),
                "sample_texts": samples[k][:3]
            }
            for k, v in counter.most_common()
        ]

    def analyze_roles(self, texts, keyword):
        """分析IP角色和通用角色，返回来源、关联话题和代表引用"""
        ip_counter = Counter()
        generic_counter = Counter()
        ip_samples = {}
        generic_samples = {}

        for t in texts:
            # IP角色
            for _, roles in IP_KEYWORDS.items():
                for r in roles:
                    if r != keyword and r in t:
                        ip_counter[r] += 1
                        if r not in ip_samples:
                            ip_samples[r] = []
                        if len(ip_samples[r]) < 3:
                            ip_samples[r].append(t[:80])
            # 通用角色
            for category, kws in GENERIC_ROLE_KEYWORDS.items():
                for kw in kws:
                    if kw in t:
                        generic_counter[kw] += 1
                        if kw not in generic_samples:
                            generic_samples[kw] = []
                        if len(generic_samples[kw]) < 2:
                            generic_samples[kw].append(t[:80])

        # 为角色查找关联话题
        def find_related_topics(texts_for_role, role_name):
            related = []
            for t in texts_for_role:
                for topic, kws in TOPIC_RULES.items():
                    if any(k in t for k in kws) and topic not in related:
                        related.append(topic)
                        if len(related) >= 3:
                            break
            return related

        ip_roles = []
        for name, count in ip_counter.most_common(10):
            ip_roles.append({
                "name": name,
                "count": count,
                "source": "IP",
                "related_topics": find_related_topics(ip_samples.get(name, []), name),
                "sample_mentions": ip_samples.get(name, [])[:2]
            })

        generic_roles = []
        for name, count in generic_counter.most_common(5):
            generic_roles.append({
                "name": name,
                "count": count,
                "source": "通用",
                "related_topics": find_related_topics(generic_samples.get(name, []), name),
                "sample_mentions": generic_samples.get(name, [])[:1]
            })

        return {"ip_roles": ip_roles, "generic_roles": generic_roles}

    def analyze_concerns(self, texts):
        """分析用户关注点，动态生成子簇视图文本"""
        result = {}

        for concern in CONCERN_RULES:
            result[concern] = {
                "count": 0,
                "samples": []
            }

        for text in texts:
            for concern, kws in CONCERN_RULES.items():
                if any(kw in text for kw in kws):
                    result[concern]["count"] += 1
                    if len(result[concern]["samples"]) < 200:
                        result[concern]["samples"].append(text)

        return self._build_concern_views(result)

    def _build_concern_views(self, concern_data):
        """动态模板生成关注点视图（替代硬编码静态文本）"""
        final_result = []

        for concern, data in concern_data.items():
            samples = data["samples"]
            cluster_rule = CONCERN_CLUSTER_RULES.get(concern, {})

            subcluster_stats = []
            for subcluster_name, kws in cluster_rule.items():
                count = 0
                kw_hits = Counter()
                for text in samples:
                    hits = [kw for kw in kws if kw in text]
                    if hits:
                        count += 1
                        kw_hits.update(hits)

                if count > 0:
                    top_kws = [kw for kw, _ in kw_hits.most_common(3)]
                    subcluster_stats.append({
                        "name": subcluster_name,
                        "count": count,
                        "percent": round(count * 100 / max(len(samples), 1), 2),
                        "top_keywords": top_kws,
                        "desc": CONCERN_CLUSTER_DESC.get(concern, {}).get(subcluster_name, ""),
                    })

            subcluster_stats.sort(key=lambda x: x["count"], reverse=True)
            top_subclusters = subcluster_stats[:4]

            # 动态生成视图文本
            views = []
            for sc in top_subclusters:
                kw_display = "、".join(sc["top_keywords"])
                view = f"{sc['name']}相关讨论占{concern}话题的{sc['percent']}%，主要涉及{kw_display}等关键词。"
                views.append(view)

            final_result.append({
                "concern": concern,
                "count": data["count"],
                "views": views,
                "subclusters": top_subclusters
            })

        return sorted(final_result, key=lambda x: x["count"], reverse=True)

    def analyze_sentiment(self, texts, SentimentAnalyzer):
        """分析情感分布、子类别和代表引用"""
        return SentimentAnalyzer.analyze_with_quotes(texts)

    # ---------------- 高频咨询（基于笔记聚类 + 高赞回答）----------------
    def analyze_questions(self, notes, comments):
        """
        高频咨询来源：先基于内容相似度对帖子聚类，找出讨论相同问题的帖子；
        再从中挑选具有咨询价值的内容；不足时按热度补充热门咨询。
        并为每个咨询取点赞/子评论数高的评论作为回答。
        """

        # 1. 准备候选帖子（降低咨询意图门槛，只要有意义内容就纳入）
        candidate_notes = []
        for n in notes:
            text = str((n.get("title") or "")) + " " + str((n.get("desc") or ""))
            text = text.strip()

            # 基础过滤：排除过短或无意义内容
            if len(text) < 15:
                continue

            # 过滤纯标点/颜文字/话题标签后检查有意义长度
            cleaned_for_check = re.sub(r'#.*?#', '', text)
            cleaned_for_check = "".join(ch for ch in cleaned_for_check if ch not in "？?。，！!~、；;：:" and ch.strip())
            if len(cleaned_for_check) < 8:
                continue

            like_count = safe_int(n.get("liked_count"))
            comment_count = safe_int(n.get("comment_count"))
            note_id = n.get("note_id")

            # 清理话题标签用于相似度计算
            text_for_sim = re.sub(r'#.*?#', '', text).strip()

            # 计算咨询价值分数（有疑问词/咨询词加分，但非必要）
            question_words = ["怎么", "如何", "哪里", "哪个", "什么", "为什么", "几岁",
                             "是不是", "好不好", "有没有", "能不能", "推荐", "适合",
                             "求问", "求助", "请教", "想问", "咨询"]
            consult_value = sum(1 for w in question_words if w in text)

            candidate_notes.append({
                "note_id": note_id,
                "text": text[:200],
                "text_for_sim": text_for_sim,
                "like_count": like_count,
                "comment_count": comment_count,
                "heat_score": like_count * 0.4 + comment_count * 0.6,
                "consult_score": consult_value
            })

        # 2. 相似度聚类（基于清理话题标签后的文本）
        clusters = self._cluster_notes(candidate_notes, threshold=0.45)

        # 3. 从聚类和单帖中选择高频咨询
        selected = []
        used_note_ids = set()

        # 优先选择相似度簇（簇大小>=2）
        clusters.sort(key=lambda c: (-len(c), -sum(n["heat_score"] for n in c)))

        for cluster in clusters:
            if len(cluster) >= 2:
                # 从簇内选咨询价值最高的作为代表
                best = max(cluster, key=lambda x: x["consult_score"] * 10 + x["heat_score"])
                best["cluster_size"] = len(cluster)
                selected.append(best)
                used_note_ids.update(n["note_id"] for n in cluster)

        # 如果聚类不够，按热度补充单条笔记
        if len(selected) < 5:
            remaining = [n for n in candidate_notes if n["note_id"] not in used_note_ids]
            remaining.sort(key=lambda x: x["heat_score"], reverse=True)
            for n in remaining[: (5 - len(selected))]:
                n["cluster_size"] = 1
                selected.append(n)

        selected = selected[:5]

        # 4. 为每个高频咨询找高赞/高回复评论作为回答
        for item in selected:
            note_id = item["note_id"]
            note_comments = [c for c in comments if c.get("note_id") == note_id]
            note_comments.sort(
                key=lambda c: safe_int(c.get("like_count")) * 0.6 + safe_int(c.get("sub_comment_count")) * 0.4,
                reverse=True
            )
            item["answers"] = []
            for c in note_comments[:3]:
                content = str(c.get("content") or "")
                if len(content.strip()) < 3:
                    continue
                item["answers"].append({
                    "text": content[:150],
                    "like_count": safe_int(c.get("like_count")),
                    "reply_count": safe_int(c.get("sub_comment_count"))
                })

        return selected

    def _cluster_notes(self, candidate_notes, threshold=0.55):
        """基于内容相似度对笔记进行简单聚类"""
        clusters = []
        visited = set()

        for i, n1 in enumerate(candidate_notes):
            if i in visited:
                continue
            cluster = [n1]
            visited.add(i)

            for j, n2 in enumerate(candidate_notes):
                if j in visited:
                    continue
                if self._similarity(n1["text"], n2["text"]) >= threshold:
                    cluster.append(n2)
                    visited.add(j)

            clusters.append(cluster)

        return clusters

    # ---------------- 新增分析维度 ----------------

    def analyze_engagement(self, notes):
        """分析笔记互动数据"""
        total_likes = sum(safe_int(n.get("liked_count")) for n in notes)
        total_collects = sum(safe_int(n.get("collected_count")) for n in notes)
        total_comments = sum(safe_int(n.get("comment_count")) for n in notes)
        total_shares = sum(safe_int(n.get("share_count")) for n in notes)

        note_count = len(notes) or 1
        avg_likes = round(total_likes / note_count, 2)
        avg_collects = round(total_collects / note_count, 2)

        # 互动等级分类
        levels = Counter()
        top_notes = []
        for n in notes:
            likes = safe_int(n.get("liked_count"))
            collects = safe_int(n.get("collected_count"))
            comments = safe_int(n.get("comment_count"))

            level = self._classify_engagement(likes, collects, comments)
            levels[level] += 1

            if level in ("爆款", "热门"):
                top_notes.append({
                    "title": (n.get("title") or "")[:40],
                    "liked": likes,
                    "collected": collects,
                    "commented": comments,
                    "shared": safe_int(n.get("share_count"))
                })

        top_notes.sort(key=lambda x: x["liked"], reverse=True)
        top_notes = top_notes[:10]

        return {
            "total_likes": total_likes,
            "total_collects": total_collects,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "avg_likes": avg_likes,
            "avg_collects": avg_collects,
            "engagement_levels": dict(levels),
            "top_notes": top_notes
        }

    def _classify_engagement(self, likes, collects, comments):
        """根据互动指标分类笔记等级"""
        rules = ENGAGEMENT_LEVEL_RULES
        if likes >= rules["爆款"]["liked_min"]:
            return "爆款"
        if likes >= rules["热门"]["liked_min"]:
            return "热门"
        if likes >= rules["普通"]["liked_min"]:
            return "普通"
        return "低互动"

    def analyze_geography(self, notes, comments):
        """分析地域分布"""
        locations = Counter()

        for n in notes:
            loc = n.get("ip_location") or ""
            if loc and loc.strip() and loc.strip() not in ("未知", "IP属地为空"):
                locations[loc.strip()] += 1

        for c in comments:
            loc = c.get("ip_location") or ""
            if loc and loc.strip() and loc.strip() not in ("未知", "IP属地为空"):
                locations[loc.strip()] += 1

        total = sum(locations.values()) or 1
        top_locations = [
            {"location": loc, "count": cnt, "percent": round(cnt * 100 / total, 2)}
            for loc, cnt in locations.most_common(15)
        ]

        return {"top_locations": top_locations, "total_with_location": total}

    def analyze_creators(self, creators):
        """分析创作者画像"""
        type_counts = Counter()
        gender_counts = Counter()
        top_creators = []

        for c in creators:
            fans = safe_int(c.get("fans"))
            interaction = safe_int(c.get("interaction"))
            gender = c.get("gender") or "未知"

            creator_type = self._classify_creator(fans)
            type_counts[creator_type] += 1
            gender_counts[gender] += 1

            if fans >= 10000:
                top_creators.append({
                    "nickname": c.get("nickname") or "",
                    "fans": fans,
                    "interaction": interaction,
                    "type": creator_type
                })

        top_creators.sort(key=lambda x: x["fans"], reverse=True)
        top_creators = top_creators[:10]

        total = sum(type_counts.values()) or 1
        type_distribution = [
            {"type": t, "count": cnt, "percent": round(cnt * 100 / total, 2)}
            for t, cnt in type_counts.most_common()
        ]

        return {
            "type_distribution": type_distribution,
            "gender_distribution": dict(gender_counts),
            "top_creators": top_creators
        }

    def _classify_creator(self, fans):
        """根据粉丝数分类创作者类型"""
        rules = CREATOR_TYPE_RULES
        if fans >= rules["头部KOL"]["fans_min"]:
            return "头部KOL"
        if fans >= rules["腰部创作者"]["fans_min"]:
            return "腰部创作者"
        if fans >= rules["初级创作者"]["fans_min"]:
            return "初级创作者"
        return "普通用户"

    def analyze_tags(self, notes):
        """分析标签分布"""
        tag_counter = Counter()

        for n in notes:
            tag_str = n.get("tag_list") or ""
            if tag_str:
                # 尝试多种分隔方式
                tags = []
                # 逗号分隔
                for t in tag_str.split(","):
                    t = t.strip()
                    if t:
                        tags.append(t)
                # 如果逗号分隔结果只有一个长字符串，尝试其他分隔符
                if len(tags) <= 1 and len(tag_str) > 20:
                    for sep in ["、", ";", "|"]:
                        parts = tag_str.split(sep)
                        if len(parts) > len(tags):
                            tags = [p.strip() for p in parts if p.strip()]
                            break
                tag_counter.update(tags)

        total = sum(tag_counter.values()) or 1
        top_tags = [
            {"tag": tag, "count": cnt, "percent": round(cnt * 100 / total, 2)}
            for tag, cnt in tag_counter.most_common(20)
        ]

        return {"top_tags": top_tags, "total_tag_occurrences": total}

    def analyze_time_trend(self, notes, comments):
        """分析时间趋势"""
        monthly_note_counts = Counter()
        monthly_comment_counts = Counter()

        for n in notes:
            ts = n.get("time")
            if ts:
                try:
                    ts_int = int(ts)
                    ts_sec = ts_int if ts_int < 1e12 else ts_int // 1000
                    dt = datetime.fromtimestamp(ts_sec)
                    month_key = dt.strftime("%Y-%m")
                    monthly_note_counts[month_key] += 1
                except (ValueError, TypeError, OSError):
                    pass

        for c in comments:
            ts = c.get("create_time")
            if ts:
                try:
                    ts_int = int(ts)
                    ts_sec = ts_int if ts_int < 1e12 else ts_int // 1000
                    dt = datetime.fromtimestamp(ts_sec)
                    month_key = dt.strftime("%Y-%m")
                    monthly_comment_counts[month_key] += 1
                except (ValueError, TypeError, OSError):
                    pass

        all_months = sorted(
            set(list(monthly_note_counts.keys()) + list(monthly_comment_counts.keys()))
        )

        trend = [
            {
                "month": m,
                "note_count": monthly_note_counts.get(m, 0),
                "comment_count": monthly_comment_counts.get(m, 0)
            }
            for m in all_months[-12:]
        ]

        # 计算趋势方向
        trend_direction = "平稳"
        growth_rate = 0.0
        if len(trend) >= 6:
            recent_3 = sum(t["comment_count"] + t["note_count"] for t in trend[-3:])
            prev_3 = sum(t["comment_count"] + t["note_count"] for t in trend[-6:-3])
            if prev_3 > 0:
                growth_rate = round((recent_3 - prev_3) * 100 / prev_3, 2)
                if growth_rate > 20:
                    trend_direction = "上升"
                elif growth_rate < -20:
                    trend_direction = "下降"

        return {
            "monthly_trend": trend,
            "trend_direction": trend_direction,
            "growth_rate": growth_rate
        }
