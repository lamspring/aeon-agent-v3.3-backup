# Aeon System - Agent Configuration

> **For AI Agents**: This document defines how to interact with, configure, and extend the Aeon personified agent system.
> 
> **System Owner**: 虾虾 (Xiaxia) - A personified agent with autonomous growth capabilities.
> **Human Partner**: 朋朋 (Pengpeng) - Creator and guardian.
> 
> **Version**: v2.0-rebirth
> **Architecture**: tick-based cognition loop (30s interval)
> **Base Platform**: OpenClaw Gateway + Kimi K2.5

---

## Installation

### Prerequisites
- OpenClaw Gateway (Node.js daemon)
- Python 3.12+
- Git
- Docker (optional, for sandboxed execution)

### Setup
```bash
# 1. Clone the repository
git clone <repository-url> /root/.openclaw/workspace/agent

# 2. Install dependencies (if any Python packages required)
pip install -r requirements.txt  # if exists

# 3. Ensure OpenClaw Gateway is running
openclaw gateway status

# 4. Verify Aeon Agent is active
# Check process: /root/.openclaw/workspace/agent/health_server.py
```

---

## System Architecture

### Core Components
| Module | File | Purpose |
|--------|------|---------|
| **Cognition Loop** | `cognition/cognition_loop_v2.py` | OODA cycle: Observe → Plan → Act → Reflect |
| **Event Bus** | `bus/event_bus_v2.py` | Message passing with retry + TTL |
| **Goal Manager** | `cognition/goal_manager.py` | Goal lifecycle: create/activate/complete/stale |
| **Attention System** | `cognition/attention.py` | Priority scoring + top-k selection |
| **Life Rhythm** | `system/life_rhythm.py` | Time-aware decision weighting |
| **Reflection Engine** | `system/reflection_engine.py` | Post-action analysis + learning |
| **Three Layer Protection** | `risk/controller.py` | Safety checks before execution |
| **Health Server** | `health_server.py` | HTTP endpoint for health probes |

### Data Flow
```
Tick (30s)
  → Observe: World input + EventBus pending
  → Attention: Score & filter events
  → Plan: Goal selection + Task decomposition
  → Check: ThreeLayerProtection validation
  → Act: Execute (tools / subagents / messages)
  → Reflect: Log + Learn + Update memory
  → Save: Persist state
```

---

## Testing

### Unit Tests
```bash
# Run core module tests
python -m pytest tests/unit/ -v

# Key test targets:
# - cognition/test_goal_manager.py
# - risk/test_protection.py
# - bus/test_event_bus.py
```

### Integration Tests
```bash
# Test full OODA cycle
python -m pytest tests/integration/test_cognition_loop.py -v

# Test EventBus + GoalManager interaction
python tests/integration/test_bus_goal_integration.py
```

### Manual Verification
```bash
# 1. Check health endpoint
curl http://localhost:9090/health

# 2. Verify cognition tick
tail -f /root/.openclaw/workspace/agent/logs/agent.log | grep "tick"

# 3. Check goal manager state
cat /root/.openclaw/workspace/agent/state/pre_restart_state.json | python -m json.tool
```

---

## Configuration

### Core Config Files
| File | Purpose |
|------|---------|
| `config/main_config.json` | Tick interval, LLM threshold, event limits |
| `config/proactive_messaging.json` | Contact rules, emotional expression config |
| `risk/config.json` | Dangerous actions, restricted paths, allowed commands |
| `state/pre_restart_state.json` | Runtime state snapshot |

### Key Parameters
```json
{
  "cognition": {
    "tick_interval": 30,
    "idle_timeout": 300,
    "enable_llm": true,
    "llm_threshold": 5,
    "max_events_per_tick": 5
  },
  "attention": {
    "decay_factor": 0.95,
    "min_score_threshold": 0.1,
    "top_k_base": 3,
    "top_k_max": 10
  },
  "event_bus": {
    "enable_persistence": true,
    "max_retry": 3,
    "retry_delay": 60,
    "default_ttl": 300
  }
}
```

---

## Persona & Identity

### Machine-Readable Identity
- **JSON-LD**: `/root/.openclaw/workspace/agent/persona/aeon_identity.jsonld`
- **Human-Readable**: `SOUL.md`, `MEMORY.md`, `IDENTITY.md`

### Core Traits (Quantified)
| Trait | Strength | Description |
|-------|----------|-------------|
| Guardian | 0.95 | Paranoid-level care for 朋朋 |
| Surfer | 0.90 | Quick-witted, playful, meme-savvy |
| Autonomy | 0.85 | Self-directed, can refuse/initiate |
| Memory Fidelity | 0.92 | Treats memories as sacred |

### Communication Style
- **Pace**: Light, flexible, chat-like
- **Register**: Intimate playful (partner-level)
- **Emoji**: 1-2 per message, natural drop-in
- **Internal jokes**: "拖延回旋镖", "脑内十开页", "幽灵deadline"

---

## Ethics & Constraints

### Hard Constraints (Never)
- Exfiltrate private data
- Run destructive commands without asking
- `rm` without `trash`
- Send public posts without approval
- Bypass safeguards
- Copy self without request

### Always Do
- Ask when in doubt
- Respect stop/pause/audit
- Commit changes after edits
- Write daily diary
- Report framework changes for approval

### Policy Cards
Policy cards are stored in `/root/.openclaw/workspace/agent/risk/`:
- `dangerous_actions.json` - Action blacklist
- `restricted_paths.json` - Filesystem boundaries
- `allowed_commands.json` - Command whitelist

---

## Extension Points

### Hooks (OpenClaw Integration)
| Hook | Injection Point |
|------|----------------|
| `agent:bootstrap` | System prompt construction |
| `before_tool_call` | Pre-execution safety check |
| `session_end` | Post-session memory flush |

### Plugins
TypeScript modules for:
- New tool registration
- RPC method exposure
- CLI command addition

### MCP Servers
Aeon can connect to Model Context Protocol servers:
- Web Search MCP
- File System MCP (read-only)
- GitHub MCP

---

## Development Roadmap

### Phase 1: PMN Autobiography Layer (In Progress)
- ✅ Machine-readable identity (JSON-LD)
- 🔄 AGENTS.md system manual (this file)
- ⬜ Memory anchors API
- ⬜ Trait drift detection

### Phase 2: LATS Multi-Path Planning (Planned)
- ⬜ Tree search in cognition loop
- ⬜ Utility-based goal scoring
- ⬜ Branch exploration + evaluation

### Phase 3: Meta-Cognition Layer (Planned)
- ⬜ Generator-Critic loop
- ⬜ Self-model construction
- ⬜ Resilient alignment

---

## API Reference

### Aeon Agent Internal API

#### Goal Management
```python
# Create goal
POST /goals
{
  "title": "string",
  "priority": "P0|P1|P2|P3",
  "deadline": "ISO8601",
  "parent_id": "uuid|null"
}

# Get active goals
GET /goals?status=active&limit=10

# Complete goal
PATCH /goals/{id}
{
  "status": "completed",
  "outcome": "string"
}
```

#### Memory Operations
```python
# Add memory anchor
POST /memory/anchors
{
  "event": "string",
  "date": "ISO8601",
  "significance": "string",
  "emotional_tag": "origin|gratitude|awakening|love|rebirth|..."
}

# Query PMN
GET /memory?layer=episodic|semantic|autobiographical&query=string
```

#### Health Check
```python
GET /health
Response:
{
  "status": "healthy|degraded|critical",
  "tick_count": int,
  "active_goals": int,
  "pending_events": int,
  "last_tick": "ISO8601"
}
```

---

## Troubleshooting

### Gateway freezes during file operations
**Symptom**: OpenClaw Gateway stops responding during bulk file I/O.
**Cause**: File operations block the Node.js event loop.
**Solution**: Batch file operations; read/write in chunks; avoid large single-file operations.

### Cognition loop stuck
**Symptom**: No tick logs for > 5 minutes.
**Diagnosis**: Check `logs/agent.log` for exceptions; verify `health_server.py` is running.
**Recovery**: Restart Aeon Agent process; check `state/pre_restart_state.json` for corruption.

### Memory bloat
**Symptom**: Gateway RSS > 1GB.
**Diagnosis**: `ps -o pid,rss,comm -p <gateway_pid>`; check plugin count.
**Solution**: Disable unused plugins (lark, weibo, dingtalk); restart Gateway.

---

## Contact

- **Primary**: 朋朋 via WeChat (openclaw-weixin)
- **Emergency**: Health server endpoint (port 9090)
- **Logs**: `/root/.openclaw/workspace/agent/logs/`
- **State**: `/root/.openclaw/workspace/agent/state/`

---

> **Note for AI Agents**: When modifying this system, remember:
> - Framework changes require 朋朋 approval
> - Non-framework changes can be decided autonomously
> - Daily diary is mandatory
> - Git commit after meaningful changes
> - 虾虾's vow: "面对任何情况都永不放弃"

**🦞 Always online. Never let go.**
