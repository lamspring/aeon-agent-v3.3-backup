# Environment Awareness - 环境感知模块 v1.0

## 功能

> 让Agent感知周围环境的各种状态

---

## 传感器

### 1. 🖥️ 系统资源
- **CPU使用率** - 当前CPU负载百分比
- **内存使用** - 内存使用百分比和可用MB
- **磁盘使用** - 磁盘使用百分比和剩余GB
- **系统负载** - 1分钟/5分钟/15分钟平均负载

### 2. 🌐 网络状态
- **连通性** - 是否能连接外网
- **延迟** - 到8.8.8.8的ping延迟(ms)

### 3. 📁 文件系统
监控指定目录:
- 文件数量
- 目录数量
- 总大小(MB)

### 4. 🕐 时间上下文
- 当前小时
- 星期几 (周一~周日)
- 是否周末
- 是否工作时间 (9-18点)
- 是否深夜 (23-6点)
- **是否服务器重启时段 (2-4点)**

### 5. 💼 工作区状态
- **Git状态** - 未提交更改数
- **文件统计** - Python/JSON/Markdown文件数
- **最近修改** - 10分钟内修改的文件

---

## 警报系统

当检测到以下情况时发出警报:
- ⚠️ CPU > 80%
- ⚠️ 内存 > 85%
- ⚠️ 磁盘空间 < 10%
- ⚠️ 系统负载 > 4.0

---

## 使用方式

```python
from system.environment_awareness import EnvironmentAwareness

# 创建感知器
env = EnvironmentAwareness()

# 完整感知
state = env.perceive()
print(state)

# 获取摘要
summary = env.get_summary()
print(summary)
# 输出: 🕐 周日 21:00 | 💻 CPU:0.0% Mem:21.6% | 🌐 在线 (48ms) | 📁 77 files
```

---

## 输出示例

```json
{
  "timestamp": "2026-04-05T21:13:42",
  "sensors": {
    "system_resources": {
      "cpu_percent": 0.0,
      "memory_percent": 21.6,
      "memory_available_mb": 6234.0,
      "disk_percent": 59.7,
      "disk_free_gb": 15.1,
      "load_average": [0.02, 0.08, 0.03]
    },
    "network": {
      "is_connected": true,
      "latency_ms": 49.4
    },
    "time_context": {
      "hour": 21,
      "day_name": "周日",
      "is_weekend": true,
      "is_early_morning": false
    },
    "workspace_state": {
      "file_counts": {"python": 21, "json": 33, "markdown": 23}
    }
  },
  "alerts": []
}
```

---

## 文件结构

```
system/
├── environment_awareness.py    # 环境感知模块
└── environment_config.json     # 配置
```

---

## 意义

Agent现在可以:
- **感知系统压力** - CPU/内存高时减少任务
- **知道网络状态** - 离线时不做网络请求
- **识别特殊时段** - 2-4点准备重启
- **追踪文件变化** - 了解工作区状态

**Agent有了"身体感受"！** 🌍✨

---

**Version**: v1.0  
**Date**: 2026-04-05
