# Simple Logger - 简化日志系统

## 设计原则

> 直接追加文本，不格式化，不总结

```
[2026-04-05 20:48:04] 系统启动
[2026-04-05 20:48:04] 执行任务: task_001
[2026-04-05 20:48:04] 步骤完成
```

---

## 使用方式

```python
from system.simple_logger import log

# 直接记录
log("系统启动")
log("执行任务: task_001")
log("步骤完成: step 1/4")
```

输出到 `logs/execution_log.txt`:
```
[2026-04-05 20:48:04] 系统启动
[2026-04-05 20:48:04] 执行任务: task_001
[2026-04-05 20:48:04] 步骤完成: step 1/4
```

---

## 获取日志

```python
from system.simple_logger import get_recent_logs

# 获取最近50行
recent = get_recent_logs(50)

# 需要总结时再处理
# ... 总结逻辑 ...
```

---

## 文件位置

```
logs/
└── execution_log.txt    # 纯文本日志
```

---

**简单、直接、不加工。**
