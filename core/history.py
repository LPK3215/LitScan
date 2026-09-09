"""
LitScan 搜索历史模块
记录每次检索的关键词/时间/源/结果数，支持历史查询和复用
"""

import json
import os
import logging
import uuid
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict

logger = logging.getLogger("litscan.history")


@dataclass
class SearchRecord:
    """一条搜索记录"""
    id: str           # 时间戳 ID
    keywords: str
    sources: list[str]
    year_from: Optional[int]
    limit_per_source: int
    total_results: int
    per_source: dict[str, int]
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SearchRecord":
        return cls(**data)


class SearchHistory:
    """搜索历史管理器"""

    def __init__(self, history_file: str = None):
        if history_file is None:
            # 默认使用 LitScan 目录下的 out/history.json（而非 CWD）
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            history_file = os.path.join(base_dir, "out", "history.json")
        self.history_file = history_file
        self.records: List[SearchRecord] = []
        self._load()

    def _load(self):
        """从文件加载历史"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.records = [SearchRecord.from_dict(r) for r in data]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"历史文件损坏，重置: {e}")
                self.records = []

    def _save(self):
        """保存到文件"""
        os.makedirs(os.path.dirname(self.history_file) or ".", exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in self.records], f, ensure_ascii=False, indent=2)

    def add(self, keywords: str, sources: list[str], year_from: Optional[int],
            limit_per_source: int, total_results: int, per_source: dict[str, int]) -> SearchRecord:
        """添加一条搜索记录"""
        now = datetime.now()
        # 使用时间戳 + UUID 前 8 位确保唯一性
        record = SearchRecord(
            id=f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            keywords=keywords,
            sources=sources,
            year_from=year_from,
            limit_per_source=limit_per_source,
            total_results=total_results,
            per_source=per_source,
            timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.records.insert(0, record)  # 最新的插前面
        self._save()
        logger.info(f"搜索记录已保存: {record.id}")
        return record

    def list(self, limit: int = 20) -> List[SearchRecord]:
        """列出最近 N 条记录"""
        return self.records[:limit]

    def get(self, record_id: str) -> Optional[SearchRecord]:
        """按 ID 获取一条记录"""
        for r in self.records:
            if r.id == record_id:
                return r
        return None

    def search_by_keywords(self, query: str) -> List[SearchRecord]:
        """按关键词搜索历史"""
        query_lower = query.lower()
        return [r for r in self.records if query_lower in r.keywords.lower()]

    def delete(self, record_id: str) -> bool:
        """删除一条记录"""
        for i, r in enumerate(self.records):
            if r.id == record_id:
                self.records.pop(i)
                self._save()
                return True
        return False

    def clear(self):
        """清空历史"""
        self.records = []
        self._save()

    def get_favorite_keywords(self) -> List[str]:
        """统计高频关键词"""
        from collections import Counter
        keywords = [r.keywords for r in self.records]
        counter = Counter(keywords)
        return [kw for kw, _ in counter.most_common(10)]

    def get_source_usage(self) -> dict[str, int]:
        """统计各源使用次数"""
        from collections import Counter
        sources = []
        for r in self.records:
            sources.extend(r.sources)
        return dict(Counter(sources).most_common())

    def __len__(self):
        return len(self.records)

    def __bool__(self):
        """始终返回 True，避免空记录时 if history: 判断为 False"""
        return True
