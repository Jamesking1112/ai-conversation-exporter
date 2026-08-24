# AI Conversation Exporter v0.1

一个用于导出 DeepSeek 网页端聊天记录的本地 Python 工具。它会获取全部会话列表和每个会话的详细消息，生成统一的 JSON，以及“每个会话一个文件”的 Markdown 备份。

这是 v0.1：当前仅支持 DeepSeek，但数据模型和目录结构已经为将来接入其他 AI 平台预留了位置。

## 你会得到什么

执行完成后，默认在 `output/` 下生成：

```text
output/
├── deepseek_conversations.json  # 标准化的完整会话数据
├── export_errors.json           # 仅在存在局部失败时生成
└── markdown/
    ├── 001_会话标题.md
    ├── 002_另一个会话.md
    └── ...
```

- `deepseek_conversations.json` 的根字段是 `schema_version`、`provider`、`exported_at` 和 `conversations`。
- 每个会话包含 ID、标题、时间、标准化消息、导出状态和原始来源字段。原始 session/message 数据会保留在 `source` 中，方便以后重新处理。
- Markdown 文件名会处理空标题、换行、Windows 非法字符、emoji、超长标题和重名；Markdown 正文中的一级标题保留原始标题。

## 环境要求

- Python 3.10 或更新版本。
- 可正常访问 `https://chat.deepseek.com`。
- 你本人已登录 DeepSeek，并能够取得自己浏览器会话对应的 Authorization 和 Cookie。

## 安装与首次配置

在项目目录打开 PowerShell，依次执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.json config.json
```

然后用编辑器打开 `config.json`，填写两个值：

```json
{
  "deepseek": {
    "authorization": "Bearer 你的完整Authorization值",
    "cookie": "你的完整Cookie字符串"
  }
}
```

请保留 `Bearer ` 前缀（如果浏览器中拿到的 Authorization 本身包含它）。`config.json` 已被 `.gitignore` 忽略，不会被正常 Git 提交；不要把它发送给任何人，也不要截图分享其中的内容。

## 运行

配置完成后，只需运行：

```powershell
python main.py
```

程序会先分页获取全部 session，再逐条获取聊天详情。它保留了原始脚本已经验证的 `fetch_page`、`history_messages`、游标分页和节流方式。

退出码含义：

- `0`：全部会话导出成功。
- `2`：任务整体完成，但有个别会话下载或 Markdown 转换失败；请查看 `output/export_errors.json`。
- `1`：配置、认证或会话列表获取失败。

## 常见问题

### 显示“Authorization 或 Cookie 已失效”

登录会话会过期。请更新 `config.json` 中的 Authorization 和 Cookie，再重新执行 `python main.py`。本项目不会在日志或错误文件中输出它们。

### 网络不稳定会怎样

网络异常、429 和 5xx 服务端错误会自动重试，默认最多重试 3 次，并逐次增加等待时间。单个聊天详情多次失败后会记录到错误清单，但不会阻止其他聊天继续导出。

### 为什么要移除旧脚本里的凭据

Authorization 和 Cookie 相当于登录凭据。将它们写入源码可能导致账号会话被他人使用。若旧脚本曾被上传、分享或截图，建议你在 DeepSeek 中刷新登录会话，并停止使用旧凭据。

## 可选配置

`config.json` 支持以下非敏感参数：

```json
{
  "request": {
    "timeout_seconds": 30,
    "max_retries": 3,
    "retry_base_delay_seconds": 1
  },
  "output_dir": "output"
}
```

- `timeout_seconds`：每个 HTTP 请求最长等待秒数。
- `max_retries`：初始请求失败后允许追加的重试次数。
- `retry_base_delay_seconds`：第一次重试前的等待秒数；之后会按 1、2、4… 倍增长。
- `output_dir`：导出目录；相对路径会以项目目录为基准。

## 开发者测试

测试不访问真实 DeepSeek，也不需要 `config.json`：

```powershell
python -m unittest discover -s tests -v
```
