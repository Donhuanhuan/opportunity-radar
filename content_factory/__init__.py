"""内容工厂统一入口

提供对外的高层 API：analyze_one / generate_one / push_to_drafts
调用示例：
    from content_factory import generate_one
    result = generate_one(opportunity_item)
"""
from content_factory.analyze import analyze, _norm_item
from content_factory.generate import generate

__all__ = ["analyze", "generate", "generate_one", "analyze_one", "_norm_item"]


def analyze_one(item: dict) -> dict:
    """分析一条商机"""
    return analyze(item)


def generate_one(item: dict, analysis: dict | None = None) -> dict:
    """生成一条商机的双版本文案"""
    return generate(item, analysis)
