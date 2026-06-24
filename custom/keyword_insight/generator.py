import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 没有 python-dotenv 时忽略，手动设置环境变量即可

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

    def run_one(self, keyword, use_llm=False, reference_content=""):

        notes, comments, creators, creator_count = self.repo.load_data(keyword)

        texts = [
            self.analyzer.clean_text((n.get("title") or "") + (n.get("desc") or ""))
            for n in notes
        ] + [
            self.analyzer.clean_text(c.get("content") or "")
            for c in comments
        ]

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

        report = ReportBuilder.build(
            keyword, notes, comments, creators,
            topics, roles, concerns, questions, sentiment,
            engagement, geography, creator_analysis, tags, time_trend,
            use_llm=use_llm,
            reference_content=reference_content,
            creator_count=creator_count,
        )

        self.save_repo.save(
            keyword, notes, comments, creators,
            topics, roles, concerns, questions,
            sentiment, report,
            engagement, geography, creator_analysis, tags, time_trend,
            mode="ai" if use_llm else "template",
        )

        print("done:", keyword)

    def run_all(self, keyword=None, use_llm=False, reference_content=""):

        keywords = self.repo.get_keywords()
        print(keywords)

        if keyword:
            if keyword in keywords:
                self.run_one(keyword, use_llm=use_llm, reference_content=reference_content)
            else:
                print(f"关键词 '{keyword}' 不在数据库中")
        else:
            for k in keywords:
                self.run_one(k, use_llm=use_llm, reference_content=reference_content)
