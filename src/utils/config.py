"""本地 config.json 的加载和校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class DeepSeekConfig:
    authorization: str
    cookie: str


@dataclass(frozen=True, slots=True)
class RequestConfig:
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_base_delay_seconds: float = 1.0


@dataclass(frozen=True, slots=True)
class AppConfig:
    deepseek: DeepSeekConfig
    request: RequestConfig
    output_dir: str = "output"


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"config.json 中的 {name} 必须是对象。")
    return value


def _positive_number(value: Any, name: str, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ConfigurationError(f"config.json 中的 {name} 必须是正数。")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"config.json 中的 {name} 必须是正数。") from error
    if parsed <= 0:
        raise ConfigurationError(f"config.json 中的 {name} 必须大于 0。")
    return parsed


def _non_negative_integer(value: Any, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ConfigurationError(f"config.json 中的 {name} 必须是大于等于 0 的整数。")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"config.json 中的 {name} 必须是大于等于 0 的整数。") from error
    if parsed < 0 or str(parsed) != str(value).strip():
        raise ConfigurationError(f"config.json 中的 {name} 必须是大于等于 0 的整数。")
    return parsed


def load_config(path: Path) -> AppConfig:
    """读取配置；所有报错均避免回显 Cookie 和 Authorization。"""
    if not path.exists():
        raise ConfigurationError(
            "未找到 config.json。请先将 config.example.json 复制为 config.json，"
            "再填写 DeepSeek 的 Authorization 和 Cookie。"
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except json.JSONDecodeError as error:
        raise ConfigurationError("config.json 不是合法 JSON，请检查逗号和引号。") from error
    except OSError as error:
        raise ConfigurationError("无法读取 config.json，请检查文件权限。") from error

    root = _mapping(raw, "根配置")
    deepseek = _mapping(root.get("deepseek"), "deepseek")
    authorization = deepseek.get("authorization")
    cookie = deepseek.get("cookie")
    if not isinstance(authorization, str) or not authorization.strip():
        raise ConfigurationError("config.json 中缺少 deepseek.authorization。")
    if not isinstance(cookie, str) or not cookie.strip():
        raise ConfigurationError("config.json 中缺少 deepseek.cookie。")

    request = _mapping(root.get("request", {}), "request")
    request_config = RequestConfig(
        timeout_seconds=_positive_number(
            request.get("timeout_seconds"), "request.timeout_seconds", 30.0
        ),
        max_retries=_non_negative_integer(
            request.get("max_retries"), "request.max_retries", 3
        ),
        retry_base_delay_seconds=_positive_number(
            request.get("retry_base_delay_seconds"),
            "request.retry_base_delay_seconds",
            1.0,
        ),
    )

    output_dir = root.get("output_dir", "output")
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise ConfigurationError("config.json 中的 output_dir 必须是非空字符串。")

    return AppConfig(
        deepseek=DeepSeekConfig(
            authorization=authorization.strip(),
            cookie=cookie.strip(),
        ),
        request=request_config,
        output_dir=output_dir.strip(),
    )
