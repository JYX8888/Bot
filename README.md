# corebot

一个面向本地代码仓库与工作区协作的轻量级 AI Agent。`corebot` 提供命令行对话、文件操作、受控 Shell、Skills 和 MCP 扩展能力，适合用来做仓库分析、代码辅助、流程自动化和私有模型接入。

## 项目亮点

- 轻量可控：聚焦本地工作区协作，不追求臃肿平台化
- 命令行优先：开箱即用，适合开发者日常使用
- 工具能力完整：文件读写、搜索、Shell 执行一体化
- 易于扩展：支持 Skills 和 MCP，可逐步接入外部能力
- 兼容开放接口：支持 OpenAI 兼容模型服务

## 它可以做什么

`corebot` 适合这些典型场景：

- 分析一个现有仓库的结构、模块职责和核心流程
- 阅读源码并回答“某个功能在哪里实现”“一段逻辑做了什么”
- 在工作区中快速搜索文件、关键字和代码入口
- 辅助修改配置、文档和小范围代码片段
- 在受限目录中执行安全命令，例如查看目录、git 状态、运行只读脚本
- 加载特定 Skills，让模型按特定工作流回答问题
- 通过 MCP 接入外部服务，把第三方能力变成可调用工具
- 作为企业内网或私有部署环境中的最小本地 Agent 基座

## 当前功能

### 基础对话能力

- 交互式 CLI 对话
- 单轮命令式提问
- 本地会话持久化，支持连续多轮协作

### 工作区工具

- 列出目录
- 读取文件
- 写入文件
- 替换文件中的文本
- 按 glob 查找文件
- 按正则搜索文件内容
- 在工作区内执行受保护的 Shell 命令

### 扩展能力

- Skills：从 `SKILL.md` 加载技能描述与工作流内容
- MCP：连接 MCP Server，并把工具 / 资源 / prompt 暴露给模型
- 自定义模型配置：支持本地 JSON 配置与环境变量

## 目录结构

```text
corebot/
  agent.py           # Agent 主循环
  cli.py             # 命令行入口
  config.py          # 配置加载
  prompts.py         # 系统提示词
  session_store.py   # 会话持久化
  skills.py          # Skills 加载与注入
  mcp.py             # MCP 连接与包装
  tools/
    files.py         # 文件相关工具
    shell.py         # Shell 工具
tests/               # 基础测试
README.md
```

## 快速开始

在项目目录下运行：

```powershell
python -m corebot --help
```

查看当前配置：

```powershell
python -m corebot status --workspace D:\path\to\your\workspace
```

启动交互式对话：

```powershell
python -m corebot chat --workspace D:\path\to\your\workspace
```

执行单轮提问：

```powershell
python -m corebot chat "帮我概括这个仓库的核心结构" --workspace D:\path\to\your\workspace
```

删除某个会话：

```powershell
python -m corebot clear-session default
```

查看当前可用 Skills：

```powershell
python -m corebot list-skills --workspace D:\path\to\your\workspace
```

## 配置方式

项目支持两种主要配置方式。

### 环境变量

- `BOT_MODEL`：模型名称，默认 `gpt-4o-mini`
- `BOT_API_KEY`：模型 API Key；未设置时回退到 `OPENAI_API_KEY`
- `BOT_BASE_URL`：OpenAI 兼容接口地址
- `BOT_MAX_TOKENS`：模型最大输出 token 数
- `BOT_DATA_DIR`：本地数据目录
- `BOT_MAX_ITERATIONS`：单次对话中工具循环的最大轮数，默认 `8`
- `BOT_SHELL_TIMEOUT`：Shell 命令超时时间，默认 `60` 秒
- `BOT_CONFIG_FILE`：配置文件路径，默认读取项目根目录下的 `bot.local.json`
- `BOT_SKILLS_DIRS`：额外 Skills 目录，多个路径用系统路径分隔符连接

如果配置了 `BOT_BASE_URL` 但没有配置 key，运行时会自动使用占位 key `EMPTY`。

### 本地 JSON 配置文件

你也可以在项目根目录放置 `bot.local.json`，集中管理模型、MCP 与 Skills 相关配置。

示例：

```json
{
  "providers": {
    "custom": {
      "apiKey": "your-api-key",
      "apiBase": "https://your-openai-compatible-endpoint/v1/"
    }
  },
  "agents": {
    "defaults": {
      "provider": "custom",
      "model": "your-model-name",
      "temperature": 0.7,
      "maxTokens": 4096
    }
  },
  "skills": {
    "dirs": ["D:/path/to/shared/skills"]
  },
  "mcpServers": {
    "demo": {
      "type": "stdio",
      "command": "python",
      "args": ["path/to/mcp_server.py"],
      "enabledTools": ["*"],
      "toolTimeout": 30
    }
  }
}
```

## Skills

### Skills 目录约定

默认会扫描以下目录中的 `SKILL.md`：

- `workspace/skills/<skill-name>/SKILL.md`
- `workspace/nanobot/skills/<skill-name>/SKILL.md`（兼容已有工作区内的技能目录结构）
- `skills.builtinDir` 指定目录
- `skills.dirs` 指定目录
- `BOT_SKILLS_DIRS` 指定目录

### Skills 触发规则

- 在问题中明确写出 skill 名称，例如 `git`、`review`、`deploy`
- 使用 `$skill_name` 形式显式引用，例如 `$git`
- 如果某个 skill 的 frontmatter 里设置了 `always: true`，则会自动加载

## MCP

`corebot` 支持在对话开始时自动连接 MCP Server，并将其提供的能力暴露给模型调用。

支持的常见传输方式：

- `stdio`
- `sse`
- `streamableHttp`

支持的常见配置字段：

- `type`
- `command`、`args`、`env`
- `url`、`headers`
- `enabledTools`
- `toolTimeout`

## 适用场景

`corebot` 特别适合作为以下项目的基础：

- 本地代码助手
- 仓库分析机器人
- 私有模型接入样板
- Skill + MCP 混合能力实验平台
- 后续扩展 WebUI / HTTP API / 消息渠道之前的核心执行层

## 当前边界

为了保持项目简单，当前版本仍然没有包含这些能力：

- WebUI
- 多聊天渠道接入
- 定时任务 / 调度系统
- 多 Agent 协作
- 完整长期记忆与复杂编排

如果后续继续扩展，`corebot` 可以自然演进为更完整的本地 Agent 系统。
