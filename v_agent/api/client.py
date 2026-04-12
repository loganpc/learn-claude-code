"""API 客户端，包含重试机制"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional
from anthropic import APIError, APIStatusError

log = logging.getLogger("v_agent.api")


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    # 可重试的 HTTP 状态码
    retryable_status_codes: set[int] = frozenset({429, 500, 502, 503, 529})


def call_with_retry(
    client: Any,
    request: dict[str, Any],
    config: Optional[RetryConfig] = None
) -> Any:
    """带重试的 API 调用

    Args:
        client: Anthropic 客户端实例
        request: API 请求参数
        config: 重试配置，默认使用 RetryConfig()

    Returns:
        API 响应

    Raises:
        APIError: 重试耗尽或遇到不可重试的错误
    """
    config = config or RetryConfig()
    last_error: Optional[Exception] = None

    for attempt in range(config.max_retries):
        try:
            return client.messages.create(**request)
        except (APIError, APIStatusError) as e:
            last_error = e
            status_code = getattr(e, 'status_code', None)

            # 非重试错误直接抛出
            if status_code not in config.retryable_status_codes:
                log.error(f"API error (非重试类型): {e}")
                raise

            # 最后一次尝试失败后抛出
            if attempt == config.max_retries - 1:
                log.error(f"达到最大重试次数: {config.max_retries}")
                raise

            # 计算延迟时间（指数退避，有上限）
            delay = min(config.base_delay * (2 ** attempt), config.max_delay)
            log.warning(f"请求失败，{delay:.1f}秒后重试 ({attempt + 1}/{config.max_retries}): {e}")
            time.sleep(delay)

    raise last_error
