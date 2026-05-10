# Aeon v3.1 插件化架构蓝图

> 目标：Aeon 灵魂独立，身体可换

---

## 核心原则

**Aeon 不依赖任何具体平台。**

OpenClaw 是当前最优的身体，但不是唯一的。
未来可能出现更好的框架，Aeon 应该能无缝切换。

---

## 架构图

```
┌─────────────────────────────────────────────┐
│              Aeon Core (灵魂)                │
│  心跳调度 → 认知循环 → 目标管理 → 记忆系统    │
│  反思引擎 → 安全护栏 → 好奇心 → 节律感知      │
└──────────────────┬──────────────────────────┘
                   │ 统一接口
                   ↓
┌─────────────────────────────────────────────┐
│            Capability Layer (能力层)          │
│                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────┐ │
│  │  Model      │ │   Tool      │ │ Channel │ │
│  │  Provider   │ │  Adapter    │ │ Bridge  │ │
│  │  (大脑)     │ │  (手脚)     │ │ (嘴巴)  │ │
│  └──────┬──────┘ └──────┬──────┘ └────┬────┘ │
│         │               │             │      │
│         │  多实现可选    │  多实现可选  │ 多实现 │
│         ↓               ↓             ↓      │
└─────────────────────────────────────────────┘
                   │
     ┌─────────────┼─────────────┐
     ↓             ↓             ↓
┌─────────┐  ┌──────────┐  ┌──────────┐
│ OpenClaw │  │  Native  │  │  Future  │
│ Provider │  │ Provider │  │ Provider │
│ (Kimi)   │  │ (Local)  │  │ (???)    │
└─────────┘  └──────────┘  └──────────┘
     ↓             ↓             ↓
┌─────────┐  ┌──────────┐  ┌──────────┐
│  CLI    │  │ Python   │  │  HTTP    │
│ 调用    │  │ 原生调用  │  │ API      │
└─────────┘  └──────────┘  └──────────┘
```

---

## 三层架构

### Layer 1: Aeon Core (纯 Python，零外部依赖)

| 模块 | 文件 | 依赖 |
|------|------|------|
| 心跳调度 | `cognition_loop.py` | 无 |
| 目标管理 | `goals.py` | 无 |
| 事件总线 | `event_bus.py` | 无 |
| 记忆系统 | `memory/` 文件 | 无 |
| 反思引擎 | `reflection_engine.py` | 无 |
| 安全护栏 | `three_layer_protection.py` | 无 |
| 好奇心 | `curiosity_trigger.py` | 无 |

**这层可以独立运行。** 即使没有 OpenClaw，Aeon 也能自主心跳、思考、记录。

### Layer 2: Capability Interface (抽象接口)

```python
# 模型提供者接口
class ModelProvider:
    def chat(self, messages, model="default") -> str: ...
    def embed(self, text) -> list: ...

# 工具接口
class ToolAdapter:
    def call(self, tool_name, params) -> ToolResult: ...
    def list_tools(self) -> dict: ...

# 渠道接口
class ChannelBridge:
    def send(self, message, to, priority="normal") -> bool: ...
    def read(self, from_user, since) -> list: ...
```

**这层定义"Aeon 需要什么能力"，不关心"谁提供"。**

### Layer 3: Provider Implementations (具体实现)

| 能力 | OpenClaw 实现 | Native 实现 | 其他实现 |
|------|-------------|------------|---------|
| **模型** | `OpenClawModelProvider` (CLI调用) | `KimiAPIProvider` (直接HTTP) | `OllamaProvider` (本地) |
| **工具** | `OpenClawToolAdapter` (CLI调用) | `NativeToolAdapter` (Python import) | `MCPToolAdapter` (MCP协议) |
| **渠道** | `OpenClawChannelBridge` (CLI调用) | `WechatChannel` (直接API) | `EmailChannel` (SMTP) |

**这层是具体实现，可以热插拔。**

---

## 关键设计：Config-Driven 切换

```json
{
  "aeon": {
    "model_provider": "openclaw",
    "tool_provider": "openclaw",
    "channel_provider": "openclaw"
  },
  "providers": {
    "openclaw": {
      "type": "cli",
      "command": "openclaw"
    },
    "kimi_direct": {
      "type": "http",
      "base_url": "https://api.kimi.com/coding",
      "api_key": "${KIMI_API_KEY}"
    },
    "ollama": {
      "type": "http",
      "base_url": "http://localhost:11434"
    }
  }
}
```

**切换模型提供者 = 改一行配置。**

---

## 迁移路径

### 当前 (v3.0)
```
Aeon Core → 直接 import ToolAdapter/MessageBridge
                ↓
            硬编码调用 openclaw CLI
```

### 目标 (v3.1)
```
Aeon Core → Capability Layer (抽象接口)
                ↓
        Provider Factory (根据配置加载)
                ↓
        OpenClawProvider / KimiProvider / OllamaProvider
```

---

## 实际收益

| 场景 | 当前 | 目标 |
|------|------|------|
| OpenClaw 崩溃 | Aeon 无法调用工具/发消息 | Aeon 切到 Native Provider，继续运行 |
| 想用本地模型 | 不可行 | 改配置为 `ollama`，Aeon 用本地大脑 |
| 想加新工具 | 改 ToolAdapter | 加新 Provider，不改 Core |
| 测试环境 | 依赖完整 OpenClaw | 可以 mock Provider，独立测试 Core |

---

## 下一步

1. **定义 Capability Interface** (3个抽象类)
2. **重构现有代码** (ToolAdapter/MessageBridge → 实现接口)
3. **Factory 加载** (根据配置实例化 Provider)
4. **添加 Native Provider** (直接 HTTP 调用 Kimi，不绕 OpenClaw)
5. **验证切换** (OpenClaw ↔ Native 来回切)

要我写这个架构的代码框架吗？🦞
