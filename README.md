# corebot

`corebot` 是一个基于 LangChain 生态重构的最小化本地智能体项目，聚焦在“本地代码仓库 / 本地工作区协作”这个核心场景。

它不是一个大而全的平台，而是一个面向开发与仓库分析任务的轻量 bot：

- 通过命令行进行对话
- 调用大模型理解代码和文件内容
- 在工作区内安全地读写文件、搜索内容、执行命令
- 保存本地会话，便于持续对话和多轮协作

## 这个项目可以做什么

`corebot` 适合以下场景：

- 分析一个已有仓库的结构、模块职责和核心流程
- 阅读源码并回答“某个功能在哪里实现”“某段逻辑做了什么”
- 在工作区内搜索文件、搜索关键字、定位代码入口
- 帮助修改文本文件或小范围代码片段
- 在受限工作区内执行命令，例如列目录、查看 git 信息、运行只读命令
- 作为一个最小可用的本地 coding bot 原型，继续扩展成更完整的 agent

如果你想做一个“类似 nanobot，但只保留最核心能力”的 bot，这个项目就是为这个目标搭的基础版本。

## 当前核心功能

目前已经具备以下能力：

- `CLI 对话`：通过命令行进行单轮或多轮聊天
- `会话持久化`：本地保存历史消息，下一次可以继续对话
- `文件工具`：
  - 列出目录
  - 读取文件
  - 写入文件
  - 替换文件中的文本
  - 按 glob 查找文件
  - 按正则搜索文件内容
- `Shell 工具`：在工作区内执行受保护的命令，并阻止高风险命令
- `模型接入`：支持 OpenAI 兼容接口，当前已兼容你本地使用的 ModelScope OpenAI 兼容地址
- `本地配置加载`：支持读取 `bot.local.json`，可复用 nanobot 风格的模型配置

## 项目结构

核心目录如下：

- `corebot/agent.py`：最小 agent 主循环，负责模型调用与工具执行
- `corebot/cli.py`：命令行入口
- `corebot/config.py`：配置加载与运行参数解析
- `corebot/prompts.py`：系统提示词
- `corebot/session_store.py`：会话持久化
- `corebot/tools/`：文件工具与 shell 工具
- `tests/`：基础测试

## 配置方式

项目支持两种配置方式。

### 1. 环境变量

可用环境变量：

- `BOT_MODEL`：模型名称，默认 `gpt-4o-mini`
- `BOT_API_KEY`：模型 API Key；如果未设置，会回退到 `OPENAI_API_KEY`
- `BOT_BASE_URL`：OpenAI 兼容接口地址
- `BOT_MAX_TOKENS`：模型最大输出 token 数
- `BOT_DATA_DIR`：本地数据目录
- `BOT_MAX_ITERATIONS`：单次对话中工具循环的最大轮数，默认 `8`
- `BOT_SHELL_TIMEOUT`：shell 命令超时时间，默认 `60` 秒
- `BOT_CONFIG_FILE`：配置文件路径，默认读取项目根目录下的 `bot.local.json`

如果使用的是本地或第三方 OpenAI 兼容接口，在配置了 `BOT_BASE_URL` 但没有设置 key 的情况下，运行时会自动使用占位 key `EMPTY`。

### 2. 本地 JSON 配置文件

你也可以在项目根目录放置一个 `bot.local.json` 文件。

`corebot` 能识别 nanobot 风格配置中的这两个部分：

- `providers.custom`
- `agents.defaults`

这样就可以直接复用已有的模型配置，而不需要每次手动导出环境变量。

## 如何运行

在 `D:\xiangmu\agent\bot` 目录下运行。

### 查看当前配置

```powershell
python -m corebot status --workspace D:\xiangmu\agent\nanobot-main
```

### 启动交互式对话

```powershell
python -m corebot chat --workspace D:\xiangmu\agent\nanobot-main
```

### 单轮提问

```powershell
python -m corebot chat "帮我概括这个仓库的核心结构" --workspace D:\xiangmu\agent\nanobot-main
```

### 删除某个会话

```powershell
python -m corebot clear-session default
```

## 适合作为哪些用途的基础

这个项目很适合作为以下工作的起点：

- 最小可用本地代码助手
- 仓库分析机器人
- 轻量版 coding agent
- 自定义企业内网 OpenAI 兼容模型接入样板
- 后续扩展 WebUI、HTTP API、消息渠道之前的核心执行层

## 当前边界

为了保持项目简单，目前没有包含这些能力：

- WebUI
- 多聊天渠道接入（如 QQ、Telegram、Discord）
- MCP
- cron / 定时任务
- 多代理协作
- 完整的记忆系统与复杂调度

这些能力可以后续继续在当前基础上往上加，但当前版本刻意只保留“最核心、最能工作的那一层”。
