"""AI Conversation Exporter v0.1 的命令行入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.converters import write_markdown_files
from src.exporters import DeepSeekExporter, ExportIssue
from src.models import ExportDocument
from src.utils.config import load_config
from src.utils.errors import AuthenticationError, ConfigurationError, ExporterError
from src.utils.http import RetryingHttpClient


PROJECT_ROOT = Path(__file__).resolve().parent


def _output_path(project_root: Path, configured_path: str) -> Path:
    """相对输出目录始终相对于项目根目录解析。"""
    path = Path(configured_path)
    return path if path.is_absolute() else project_root / path


def _write_json(path: Path, payload: object) -> None:
    """使用 UTF-8 和易读缩进写入 JSON。"""
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _all_issues(
    export_issues: Iterable[ExportIssue], conversion_issues: Iterable[object]
) -> list[dict[str, object]]:
    """将两个阶段的错误对象转换为可写入 JSON 的安全结构。"""
    issues: list[dict[str, object]] = [issue.to_dict() for issue in export_issues]
    for issue in conversion_issues:
        to_dict = getattr(issue, "to_dict", None)
        if callable(to_dict):
            issues.append(to_dict())
    return issues


def run(project_root: Path = PROJECT_ROOT) -> int:
    """执行一次完整导出，返回为脚本和自动化准备的退出码。"""
    print("=" * 36)
    print("AI Conversation Exporter v0.1")
    print("DeepSeek 全量导出")
    print("=" * 36)

    try:
        config = load_config(project_root / "config.json")
    except ConfigurationError as error:
        print(f"配置错误：{error}")
        return 1

    output_dir = _output_path(project_root, config.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        print("输出错误：无法创建输出目录，请检查 output_dir 和文件权限。")
        return 1

    exporter = DeepSeekExporter(
        config.deepseek,
        RetryingHttpClient(config.request),
    )

    try:
        export_result = exporter.export_conversations()
    except AuthenticationError:
        print("认证失败：Authorization 或 Cookie 已失效，请更新 config.json 后重试。")
        return 1
    except ExporterError as error:
        print(f"导出失败：{error}")
        return 1
    except Exception:
        print("导出失败：发生未预料的启动级错误，未输出可能不完整的数据。")
        return 1

    try:
        json_path = output_dir / "deepseek_conversations.json"
        _write_json(json_path, ExportDocument(export_result.conversations).to_dict())

        markdown_dir = output_dir / "markdown"
        conversion_result = write_markdown_files(export_result.conversations, markdown_dir)

        issues = _all_issues(export_result.issues, conversion_result.issues)
        if issues:
            _write_json(output_dir / "export_errors.json", issues)
    except OSError:
        print("输出错误：无法写入导出文件，请检查输出目录权限。")
        return 1
    except Exception:
        print("输出错误：导出数据写入过程中发生未知错误。")
        return 1

    print("\n" + "=" * 36)
    print("导出完成")
    print(f"会话总数: {len(export_result.conversations)}")
    print(f"Markdown: {conversion_result.written_count} 个文件")
    print(f"异常数量: {len(issues)}")
    print(f"标准 JSON: {json_path}")
    print(f"Markdown 目录: {markdown_dir}")
    if issues:
        print(f"错误清单: {output_dir / 'export_errors.json'}")
        print("任务已完成，但有部分会话未成功导出。")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
