"""
LitScan 核心检索模块
HTTP GET + 智能重试 + 限流处理 + 友好错误提示
"""

import os
import time
import logging
from typing import Optional, Callable

import requests

logger = logging.getLogger("litscan.fetcher")


class FetchError(Exception):
    """检索失败"""
    def __init__(self, message, retries_done=0, last_status=0):
        super().__init__(message)
        self.retries_done = retries_done
        self.last_status = last_status


class RateLimitInfo:
    """限流信息"""
    def __init__(self, source, wait_seconds, attempt, max_attempts):
        self.source = source
        self.wait_seconds = wait_seconds
        self.attempt = attempt
        self.max_attempts = max_attempts

    def __str__(self):
        return f"[{self.source}] 限流等待 {self.wait_seconds}s (第{self.attempt}/{self.max_attempts}次)"


def _get_proxies(proxy=None):
    """获取代理配置"""
    if proxy:
        return {"http": proxy, "https": proxy}
    http_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    https_proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if http_proxy or https_proxy:
        return {"http": http_proxy, "https": https_proxy}
    return None


def fetch(url, params=None, headers=None, timeout=45, max_retries=4,
          retry_delay=8.0, user_agent="LitScan/1.0", proxy=None,
          on_rate_limit=None, on_retry=None, source_name="", year_from=None):
    """
    HTTP GET + 智能重试 + 限流处理

    on_rate_limit: 限流回调 fn(RateLimitInfo)
    on_retry: 重试回调 fn(attempt, max_attempts, reason)
    source_name: 来源名（用于日志和回调）
    """
    if headers is None:
        headers = {}
    if "User-Agent" not in headers:
        headers["User-Agent"] = user_agent

    # 代理: 显传 "none" 字符串则不走代理
    if proxy == "none":
        proxies = {"http": None, "https": None}
    else:
        proxies = _get_proxies(proxy)

    last_exception = None
    last_status = 0

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"[{source_name}] try {attempt}/{max_retries} GET {url}")
            resp = requests.get(url, params=params, headers=headers,
                                timeout=timeout, proxies=proxies)

            # 429 限流
            if resp.status_code == 429:
                wait_time = retry_delay * attempt
                info = RateLimitInfo(source_name, wait_time, attempt, max_retries)
                if on_rate_limit:
                    on_rate_limit(info)
                else:
                    print(f"   {info}")
                time.sleep(wait_time)
                last_status = 429
                continue

            # 5xx 服务器错误
            if resp.status_code >= 500:
                last_status = resp.status_code
                if attempt < max_retries:
                    delay = retry_delay * attempt
                    if on_retry:
                        on_retry(attempt, max_retries, f"HTTP {resp.status_code}")
                    time.sleep(delay)
                    continue

            # 4xx 客户端错误
            if resp.status_code >= 400:
                last_status = resp.status_code
                if attempt < max_retries:
                    delay = retry_delay * attempt
                    if on_retry:
                        on_retry(attempt, max_retries, f"HTTP {resp.status_code}")
                    time.sleep(delay)
                    continue

            resp.raise_for_status()
            logger.info(f"[{source_name}] OK  len={len(resp.content)}")
            return resp

        except requests.exceptions.Timeout as e:
            last_exception = e
            if attempt < max_retries and on_retry:
                on_retry(attempt, max_retries, "请求超时")
            if attempt < max_retries:
                time.sleep(retry_delay * attempt)

        except requests.exceptions.SSLError as e:
            last_exception = e
            if attempt < max_retries and on_retry:
                on_retry(attempt, max_retries, f"SSL 错误")
            if attempt < max_retries:
                time.sleep(retry_delay * attempt)

        except requests.exceptions.ConnectionError as e:
            last_exception = e
            if attempt < max_retries and on_retry:
                on_retry(attempt, max_retries, "连接失败")
            if attempt < max_retries:
                time.sleep(retry_delay * attempt)

        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < max_retries and on_retry:
                on_retry(attempt, max_retries, str(e)[:100])
            if attempt < max_retries:
                time.sleep(retry_delay * attempt)

    raise FetchError(
        f"[{source_name}] 检索失败，已重试 {max_retries} 次",
        retries_done=max_retries,
        last_status=last_status,
    )
