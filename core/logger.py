"""
LitScan 操作日志模块
记录所有检索操作和系统事件
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

logger = logging.getLogger("litscan.logger")


class LogLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"
    PROGRESS = "PROGRESS"


@dataclass
class LogEntry:
    """一条日志记录"""
    id: str
    timestamp: str
    level: str
    message: str
    source: str = ""          # 触发来源: search/api/system
    details: dict = None      # 额外详情

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("details") is None:
            d.pop("details")
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LogEntry":
        return cls(**data)


class OperationLogger:
    """操作日志管理器"""

    def __init__(self, log_file: str = None):
        if log_file is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_file = os.path.join(base_dir, "out", "operations.json")
        self.log_file = log_file
        self.entries: List[LogEntry] = []
        self._load()

    def _load(self):
        """从文件加载日志"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.entries = [LogEntry.from_dict(r) for r in data]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"日志文件损坏，重置: {e}")
                self.entries = []

    def _save(self):
        """保存到文件"""
        os.makedirs(os.path.dirname(self.log_file) or ".", exist_ok=True)
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in self.entries], f, ensure_ascii=False, indent=2)

    def _next_id(self) -> str:
        """生成下一个日志 ID"""
        import uuid
        return f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def log(self, level: LogLevel, message: str, source: str = "system", details: dict = None) -> LogEntry:
        """添加一条日志"""
        entry = LogEntry(
            id=self._next_id(),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            level=level.value,
            message=message,
            source=source,
            details=details,
        )
        self.entries.insert(0, entry)  # 最新的插前面
        # 限制日志数量，最多保留 500 条
        if len(self.entries) > 500:
            self.entries = self.entries[:500]
        self._save()
        return entry

    def info(self, message: str, source: str = "system", details: dict = None) -> LogEntry:
        return self.log(LogLevel.INFO, message, source, details)

    def warning(self, message: str, source: str = "system", details: dict = None) -> LogEntry:
        return self.log(LogLevel.WARNING, message, source, details)

    def error(self, message: str, source: str = "system", details: dict = None) -> LogEntry:
        return self.log(LogLevel.ERROR, message, source, details)

    def success(self, message: str, source: str = "system", details: dict = None) -> LogEntry:
        return self.log(LogLevel.SUCCESS, message, source, details)

    def progress(self, message: str, source: str = "search", details: dict = None) -> LogEntry:
        return self.log(LogLevel.PROGRESS, message, source, details)

    def list(self, limit: int = 50, level: str = None, source: str = None) -> List[LogEntry]:
        """列出日志，支持筛选"""
        result = self.entries
        if level:
            result = [e for e in result if e.level == level]
        if source:
            result = [e for e in result if e.source == source]
        return result[:limit]

    def clear(self):
        """清空日志"""
        self.entries = []
        self._save()

    def __len__(self):
        return len(self.entries)

    def __bool__(self):
        return True
