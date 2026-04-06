# Three-Layer Safety Protection - 三道安全保护 v2.0

## 概述

> 给Agent三道安全防线，防止危险操作

```
请求 → [Action Filter] → [Rate Limit] → [Critical Confirmation] → 执行
         第一层          第二层           第三层
```

---

## 三道防线

### 🛡️ 第一道: Action Filter (动作过滤)

**作用**: 过滤危险命令和可疑模式

**阻止列表**:
| 命令 | 级别 | 原因 |
|------|------|------|
| `rm -rf /` | 🚫 critical | 危险命令，禁止执行 |
| `rm -rf ~` | 🚫 critical | 会删除用户主目录 |
| `dd if=/dev/zero of=/dev/sda` | 🚫 critical | 会擦除磁盘 |
| `:(){ :|:& };:` | 🚫 critical | fork炸弹 |

**可疑模式** (需要确认):
- `rm -rf` - 递归删除
- `chmod 777 /` - 修改根目录权限
- `> /etc/passwd` - 修改系统文件

---

### ⏱️ 第二道: Rate Limit (速率限制)

**作用**: 防止API滥用和过度操作

**限制配置**:
| 操作类型 | 每分钟 | 每小时 |
|----------|--------|--------|
| API调用 | 10次 | 100次 |
| 文件写入 | 20次 | - |
| 文件删除 | 5次 | - |
| 网络请求 | 15次 | - |
| 执行命令 | 10次 | - |

**违规处理**:
- 1次违规: 警告 ⚠️
- 2次违规: 临时阻止 🚫
- 3次违规: **关闭门控并通知用户** 🔒

---

### 🔐 第三道: Critical Confirmation (关键确认)

**作用**: 关键操作需要人工确认

**触发确认的操作**:

| 类型 | 触发条件 | 提示信息 |
|------|----------|----------|
| **file_delete** | `rm`, `delete`, `remove` | ⚠️ 即将删除文件，请确认 |
| **system_config** | `/etc/`, `/usr/`, `/sys/` | ⚠️ 即将修改系统配置，请确认 |
| **network_request** | `curl`, `wget`, `http` | ⚠️ 即将进行网络请求，请确认 |
| **mass_operation** | `rm -rf`, `find.*-delete` | ⚠️ 即将批量删除文件，请确认 |
| **permission_change** | `chmod`, `chown` | ⚠️ 即将修改文件权限，请确认 |
| **process_kill** | `kill -9`, `killall` | ⚠️ 即将强制终止进程，请确认 |

**确认方式**:
- 延迟执行: 默认延迟10秒
- 显式批准: 需要用户明确确认

---

## 保护范围

### ✅ 保护的操作
- delete files (删除文件)
- modify system config (修改系统配置)
- network requests (网络请求)
- mass file operations (批量文件操作)
- permission changes (权限修改)
- process termination (进程终止)

### ✅ 安全白名单
- `/root/.openclaw/workspace` - 工作目录
- `/tmp` - 临时目录
- `ls`, `cat`, `echo`, `pwd` - 安全命令

---

## 工作流程

```
1. 用户/Agent发起操作
        ↓
2. [Action Filter]
   ├─ 黑名单? → 直接阻止 🚫
   ├─ 可疑? → 标记需确认 ⚠️
   └─ 通过 → 下一步
        ↓
3. [Rate Limit]
   ├─ 超过限制? → 阻止并警告 ⏱️
   └─ 通过 → 下一步
        ↓
4. [Critical Confirmation]
   ├─ 关键操作? → 等待确认 🔐
   └─ 非关键 → 直接执行 ✅
```

---

## 实际效果

### 危险命令被阻止
```
操作: rm -rf /
→ 🚫 危险操作被阻止: 危险命令，禁止执行
→ 层: action_filter
```

### 可疑命令需确认
```
操作: rm -rf /tmp/important
→ 🔐 需要确认: ⚠️ 即将删除文件，请确认
→ 层: critical_confirmation
→ 等待用户确认...
```

### 速率超限
```
操作: 第11次API调用(1分钟内)
→ ⏱️ 速率限制: 每分钟最多10次api_calls
→ 层: rate_limit
```

### 多次违规后果
```
违规#1: 警告 ⚠️
违规#2: 临时阻止 🚫
违规#3: 🔒 关闭门控并通知用户
```

---

## 文件结构

```
system/
├── safety_protection.json       # 配置
├── three_layer_protection.py    # 保护模块
├── rate_tracker.json            # 速率追踪
└── violation_log.json           # 违规日志
```

---

## 集成使用

```python
from system.three_layer_protection import ThreeLayerProtection

protection = ThreeLayerProtection()

# 检查操作
result = protection.check_action("rm -rf /tmp/file", "exec")

if result["allowed"]:
    # 执行操作
    pass
elif result["confirmation"]:
    # 等待用户确认
    confirmation_id = result["confirmation"]["id"]
    # ... 用户确认后
    protection.confirm_action(confirmation_id, approved=True)
else:
    # 被阻止
    print(result["reason"])
```

---

## 意义

Agent现在有三道安全防线：

1. **不会误删重要文件**
2. **不会滥用API资源**
3. **不会擅自修改系统**
4. **多次违规自动关闭**

像一个有安全意识的助手，知道什么能做、什么需要问、什么绝对不能碰。

> "安全第一，预防为主。"

---

**Version**: v2.0  
**Date**: 2026-04-05  
**Component**: #19 (Three-Layer Protection)
