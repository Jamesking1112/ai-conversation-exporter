"""带有限重试的 HTTP 客户端。"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

import requests

from .config import RequestConfig
from .errors import AuthenticationError, RequestFailedError


class RetryingHttpClient:
    """保持 requests 行为，同时只为临时故障增加有限重试。"""

    def __init__(
        self,
        config: RequestConfig,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._sleep = sleep

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None = None,
    ) -> requests.Response:
        """GET 请求。认证失败不重试，网络和临时服务错误会重试。"""
        total_attempts = self._config.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(total_attempts):
            try:
                response = self._session.get(
                    url,
                    headers=dict(headers),
                    params=dict(params) if params is not None else None,
                    timeout=self._config.timeout_seconds,
                )
            except requests.RequestException as error:
                last_error = error
                if attempt < total_attempts - 1:
                    self._sleep(self._config.retry_base_delay_seconds * (2**attempt))
                    continue
                raise RequestFailedError("网络请求失败，已达到最大重试次数。") from error

            if response.status_code in (401, 403):
                raise AuthenticationError(
                    "Authorization 或 Cookie 已失效，请更新 config.json 后重试。"
                )

            if 200 <= response.status_code < 300:
                return response

            is_retryable_status = response.status_code == 429 or 500 <= response.status_code < 600
            if is_retryable_status and attempt < total_attempts - 1:
                self._sleep(self._config.retry_base_delay_seconds * (2**attempt))
                continue

            raise RequestFailedError(
                f"请求失败（HTTP {response.status_code}），已停止当前请求。"
            )

        # 理论上不会到达这里，保留该分支让静态分析和未来维护更清晰。
        raise RequestFailedError("网络请求失败，已达到最大重试次数。") from last_error
