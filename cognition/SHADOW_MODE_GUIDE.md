# Shadow Mode 集成指南

## 状态

✅ **影子模式已完成并测试通过**

文件：`agent/cognition/cognition_loop_shadow.py`

## 测试验证

```
普通模式：shadow=False → 正常运行
影子模式：shadow=True → 5次 tick 全部成功
  - 平均耗时：736ms
  - 错误率：0%
  - 感知模块工作正常（检测到 body pain）
```

## 如何启用

### 方法 1：修改 Gateway Bridge（推荐）

编辑 `agent/gateway_bridge.py`：

```python
# 旧导入
# from cognition.cognition_loop_v2 import get_cognition

# 新导入（启用影子模式）
from cognition.cognition_loop_shadow import get_cognition_shadow as get_cognition
```

然后在 `bridge_gateway()` 函数里：
```python
# 初始化时启用影子模式
cognition = get_cognition_shadow(shadow_mode=True)
```

### 方法 2：修改 Health Server

编辑 `agent/health_server.py`：

```python
# 旧导入
# from cognition.cognition_loop_v2 import get_cognition

# 新导入
from cognition.cognition_loop_shadow import get_cognition_shadow as get_cognition
```

### 方法 3：运行时切换（无需修改代码）

在 AEON 启动后，通过 aeon-cli：

```bash
cd /root/.openclaw/workspace/agent
python3 -c "
from cognition.cognition_loop_shadow import get_cognition_shadow
from cognition.cognition_loop_v2 import set_cognition

# 创建影子模式实例，替换全局实例
shadow = get_cognition_shadow(shadow_mode=True)
set_cognition(shadow)
print('Shadow mode enabled')
"
```

## 监控

启用影子模式后，可以通过 Health Server 查看影子状态：

```bash
curl -s http://localhost:9090/api/status | python3 -m json.tool
```

响应中会包含：
```json
{
  "shadow_mode": true,
  "shadow_report": {
    "status": "running",
    "total_shadow_ticks": 1250,
    "plan_rate": 15.2,
    "execution_rate": 8.5,
    "error_rate": 0.0,
    "avg_elapsed_ms": 45.3
  }
}
```

## 切换时机

当 `shadow_report.equivalence_score` 连续 3 天 > 95 时：
1. 修改 `cognition_loop_shadow.py`：`shadow_mode` 默认改为 `False`
2. 或直接替换 `get_cognition()` 返回纯新模块链
3. 废弃旧 `cognition_loop_v2.py`

## 文件清单

| 文件 | 说明 |
|------|------|
| `cognition_loop_shadow.py` | 影子模式包装器（核心） |
| `orchestrator.py` | 新编排器 v2.0 |
| `perception.py` | 新感知模块 v2.0 |
| `planning.py` | 新规划模块 v2.0 |
| `execution.py` | 新执行模块 v2.0 |
| `reflection.py` | 新反思模块 v2.0 |
| `shadow_migration.py` | 独立迁移工具（备用） |

---

作者：虾虾
日期：2026-04-30
