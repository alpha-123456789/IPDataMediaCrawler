from custom.keyword_insight.config import EMOTION_KEYWORDS


class SentimentAnalyzer:

    POSITIVE_WORDS = [
        # 基础正面
        "好", "喜欢", "优秀", "棒", "不错", "推荐", "可爱",
        # 赞叹类
        "惊艳", "绝了", "超赞", "太棒了", "厉害", "神作", "完美",
        # 喜爱类
        "爱", "值得", "好看", "精彩", "赞", "满分", "一流", "顶",
        # 温暖类
        "暖心", "感动", "治愈", "温馨", "甜蜜", "幸福", "正能量",
        # 实用类
        "实用", "有用", "有帮助", "干货", "受益", "学到", "启发",
        # 推荐类
        "强烈推荐", "必看", "安利", "入手", "收藏", "分享给大家",
        # 儿童正面
        "适合孩子", "孩子喜欢", "宝宝爱看", "小朋友喜欢"
    ]

    NEGATIVE_WORDS = [
        # 基础负面
        "差", "垃圾", "讨厌", "无聊", "糟糕",
        # 强负面
        "恶心", "骗", "坑", "骗局", "坑人", "黑心", "欺诈",
        # 不满类
        "失望", "不满", "差劲", "不值", "浪费", "后悔", "不值这个价",
        # 担忧类
        "害怕", "吓人", "恐怖", "担心", "恐惧", "紧张", "噩梦",
        # 批评类
        "粗糙", "敷衍", "劣质", "难看", "丑", "敷衍了事", "糊弄",
        # 质疑类
        "看不懂", "迷惑", "困惑", "不理解", "费解", "混乱",
        # 儿童负面
        "不适合孩子", "孩子不喜欢", "宝宝不看", "太吓人了"
    ]

    INTENSITY_WORDS = {
        "amplify": ["太", "非常", "特别", "超级", "极其", "真的", "实在", "相当", "格外", "极度"],
        "dampen": ["有点", "稍微", "一般", "还行", "勉强", "凑合", "略微", "部分"]
    }

    NEGATION_WORDS = ["不", "没", "不是", "没有", "并非", "不会", "不能", "不太", "不怎么", "未必"]

    @classmethod
    def _check_negation(cls, text, word, pos):
        """检查情感词前3-5个字符内是否有否定词"""
        start = max(0, pos - 5)
        prefix = text[start:pos]
        return any(neg in prefix for neg in cls.NEGATION_WORDS)

    @classmethod
    def _check_intensity(cls, text, word, pos):
        """检查情感词前3-5个字符内是否有强度词，返回放大/减弱系数"""
        start = max(0, pos - 5)
        prefix = text[start:pos]
        for amp in cls.INTENSITY_WORDS["amplify"]:
            if amp in prefix:
                return 1.5
        for damp in cls.INTENSITY_WORDS["dampen"]:
            if damp in prefix:
                return 0.5
        return 1.0

    @classmethod
    def analyze(cls, text: str):
        if not text:
            return 'neutral', 0.5

        text = str(text)

        pos_score = 0.0
        neg_score = 0.0

        for w in cls.POSITIVE_WORDS:
            idx = 0
            while True:
                idx = text.find(w, idx)
                if idx == -1:
                    break
                intensity = cls._check_intensity(text, w, idx)
                if cls._check_negation(text, w, idx):
                    neg_score += 0.5 * intensity
                else:
                    pos_score += 1.0 * intensity
                idx += len(w)

        for w in cls.NEGATIVE_WORDS:
            idx = 0
            while True:
                idx = text.find(w, idx)
                if idx == -1:
                    break
                intensity = cls._check_intensity(text, w, idx)
                if cls._check_negation(text, w, idx):
                    pos_score += 0.5 * intensity
                else:
                    neg_score += 1.2 * intensity
                idx += len(w)

        total = pos_score + neg_score

        if total == 0:
            return 'neutral', 0.5

        score = pos_score / (pos_score + neg_score + 0.1)

        if score > 0.6:
            return 'positive', min(score, 1.0)
        elif score < 0.4:
            return 'negative', max(1 - score, 0.0)
        else:
            return 'neutral', 0.5

    @classmethod
    def analyze_emotion_subcategories(cls, texts):
        """统计每个情感子类别的命中次数和代表性文本"""
        result = {}
        for subcat, words in EMOTION_KEYWORDS.items():
            count = 0
            samples = []
            for text in texts:
                text = str(text) if text else ""
                hits = [w for w in words if w in text]
                if hits:
                    count += 1
                    if len(samples) < 5:
                        samples.append({
                            "text": text[:120],
                            "keywords": hits[:3]
                        })
            result[subcat] = {"count": count, "samples": samples}
        return result

    @classmethod
    def analyze_with_quotes(cls, texts):
        """情感分布 + 前5条正面/负面代表性引用 + 情感子类别细分"""
        stats = {"positive": 0, "neutral": 0, "negative": 0}
        pos_quotes = []
        neg_quotes = []

        for t in texts:
            label, score = cls.analyze(t)
            stats[label] += 1
            text_str = str(t)[:100] if t else ""
            if label == "positive" and score > 0.7:
                pos_quotes.append((score, text_str))
            elif label == "negative" and score < 0.3:
                neg_quotes.append((1 - score, text_str))

        pos_quotes.sort(key=lambda x: x[0], reverse=True)
        neg_quotes.sort(key=lambda x: x[0], reverse=True)

        total = sum(stats.values()) or 1
        distribution = {k: round(v * 100 / total, 2) for k, v in stats.items()}

        emotion_subcategories = cls.analyze_emotion_subcategories(texts)

        return {
            "distribution": distribution,
            "positive_quotes": [q[1] for q in pos_quotes[:5]],
            "negative_quotes": [q[1] for q in neg_quotes[:5]],
            "emotion_subcategories": emotion_subcategories
        }
