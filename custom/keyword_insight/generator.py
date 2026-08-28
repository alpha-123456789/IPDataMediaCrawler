import os
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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

    def run_one(self, keyword, use_llm=True, reference_content="", report_month=None):
        report_month = report_month or datetime.now().strftime("%Y-%m")
        notes, comments, creators, creator_count = self.repo.load_data(keyword, report_month)
        if not notes and not comments:
            print(f"skip: {keyword} / {report_month}（本月无新增数据）")
            return False
        texts = [self.analyzer.clean_text((n.get("title") or "") + (n.get("desc") or "")) for n in notes] + [self.analyzer.clean_text(c.get("content") or "") for c in comments]
        topics = self.analyzer.analyze_topics(texts)
        roles = self.analyzer.analyze_roles(texts, keyword)
        concerns = self.analyzer.analyze_concerns(notes, comments)
        questions = self.analyzer.analyze_questions(notes, comments)
        sentiment = self.analyzer.analyze_sentiment(texts, SentimentAnalyzer)
        engagement = self.analyzer.analyze_engagement(notes)
        geography = self.analyzer.analyze_geography(notes, comments)
        creator_analysis = self.analyzer.analyze_creators(creators)
        tags = self.analyzer.analyze_tags(notes)
        time_trend = self.analyzer.analyze_time_trend(notes, comments)
        report = ReportBuilder.build(keyword, notes, comments, creators, topics, roles, concerns, questions, sentiment, engagement, geography, creator_analysis, tags, time_trend, use_llm=True, reference_content=reference_content, creator_count=creator_count)
        self.save_repo.save(keyword, report_month, notes, comments, creators, topics, roles, concerns, questions, sentiment, report, engagement, geography, creator_analysis, tags, time_trend, mode="ai")
        print(f"done: {keyword} / {report_month}")
        return True

    def run_all(self, keyword=None, use_llm=True, reference_content="", report_month=None):
        for item in ([keyword] if keyword else self.repo.get_keywords()):
            self.run_one(item, use_llm=True, reference_content=reference_content, report_month=report_month)
