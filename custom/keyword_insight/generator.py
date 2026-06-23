from custom.keyword_insight.sentiment import SentimentAnalyzer
from custom.keyword_insight.repository import KeywordRepository
from custom.keyword_insight.analyzer import Analyzer
from custom.keyword_insight.report_builder import ReportBuilder
from custom.keyword_insight.report_repository import ReportRepository


class Generator:

    def __init__(self):
        self.repo = KeywordRepository()
        self.analyzer = Analyzer()
        self.save_repo = ReportRepository()

    def run_one(self, keyword):

        notes, comments, creators = self.repo.load_data(keyword)

        texts = [
            (n.get("title") or "") + (n.get("desc") or "")
            for n in notes
        ] + [
            c.get("content") or ""
            for c in comments
        ]

        # 5个现有分析维度（升级后）
        topics = self.analyzer.analyze_topics(texts)
        roles = self.analyzer.analyze_roles(texts, keyword)
        concerns = self.analyzer.analyze_concerns(texts)
        questions = self.analyzer.analyze_questions(notes, comments)
        sentiment = self.analyzer.analyze_sentiment(texts, SentimentAnalyzer)

        # 5个新增分析维度
        engagement = self.analyzer.analyze_engagement(notes)
        geography = self.analyzer.analyze_geography(notes, comments)
        creator_analysis = self.analyzer.analyze_creators(creators)
        tags = self.analyzer.analyze_tags(notes)
        time_trend = self.analyzer.analyze_time_trend(notes, comments)

        report = ReportBuilder.build(
            keyword, notes, comments, creators,
            topics, roles, concerns, questions, sentiment,
            engagement, geography, creator_analysis, tags, time_trend
        )

        self.save_repo.save(
            keyword, notes, comments, creators,
            topics, roles, concerns, questions,
            sentiment, report,
            engagement, geography, creator_analysis, tags, time_trend
        )

        print("done:", keyword)

    def run_all(self, keyword=None):

        keywords = self.repo.get_keywords()
        print(keywords)

        if keyword:
            if keyword in keywords:
                self.run_one(keyword)
            else:
                print(f"关键词 '{keyword}' 不在数据库中")
        else:
            for k in keywords:
                self.run_one(k)
