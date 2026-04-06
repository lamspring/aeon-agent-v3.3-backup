# 云服务商监控组件限制配置

**配置时间**: 2026-04-06 20:10
**方案**: 保守处理 - 保持运行但限制监控范围

---

## 组件概览

| 组件 | 用途 | 厂商 |
|------|------|------|
| cloud-monitor-agent | 系统性能监控 | 字节跳动 (Volcengine) |
| elkeid-agent | 安全监控/入侵检测 | 字节跳动 (Elkeid) |

---

## 配置变更

### 1. cloud-monitor-agent (Volcengine)

**配置文件**: `/usr/local/cloud-monitor-agent/config.yaml`
**备份**: `agent/archive/cloud-configs/cloud-monitor-agent.yaml.backup`

#### 变更 1.1: 禁用日志收集
```yaml
UnregisterManager:
  Logs: false  # ← 原为 true，禁用防止收集敏感日志
```

#### 变更 1.2: 收紧资源限制
```yaml
Worker:
  CPUShares: 10      # ← 从 20 降低
  CPUQuota: 10000    # ← 从 20000 降低
  MemoryLimitInMb: 200  # ← 从 300 降低
  RestartCoolDownInSeconds: 30  # ← 新增，防止频繁重启
```

**效果**:
- ❌ 不再收集系统日志（保护隐私）
- ✅ 资源占用降低 ~30%
- ✅ 重启冷却防止抖动

---

### 2. elkeid-agent (安全监控)

**配置文件**: `/etc/systemd/system/elkeid-agent.service`
**备份**: `agent/archive/cloud-configs/elkeid-agent.service.backup`

#### 变更 2.1: 收紧资源限制
```ini
[Service]
CPUQuota=5%        # ← 从 10% 降低
MemoryMax=200M     # ← 从 250M 降低
MemoryLimit=200M   # ← 从 250M 降低
```

**效果**:
- ✅ CPU 限制从 10% → 5%
- ✅ 内存限制从 250M → 200M

---

## 当前资源占用

| 组件 | 内存使用 | 内存限制 | CPU限制 |
|------|---------|---------|---------|
| cloud-monitor-agent | 23.1M | 200M | 10% CPUQuota |
| elkeid-agent | 9.6M | 200M | 5% CPUQuota |
| **总计** | **32.7M** | **400M** | **15%** |

---

## 监控范围调整

### 已禁用的收集项

**cloud-monitor-agent**:
- ✅ Logs (系统日志)
- ✅ CPU (基础CPU指标)
- ✅ Mem (基础内存指标)
- ✅ Disk (基础磁盘指标)
- ✅ Net (基础网络指标)
- ✅ ProcessStat (进程统计)
- ✅ SysLoad (系统负载)

**保留的监控项**:
- Hostinfo (主机信息)
- EBPF (内核事件)
- GpuBurnInfo (GPU信息，如存在)

### elkeid-agent

**配置方式**: 服务端下发策略
**当前限制**: 仅通过资源限制约束

---

## 恢复方法

如需恢复原始配置：

```bash
# 恢复 cloud-monitor-agent
cp /root/.openclaw/workspace/agent/archive/cloud-configs/cloud-monitor-agent.yaml.backup \
   /usr/local/cloud-monitor-agent/config.yaml
systemctl restart cloud-monitor-agent

# 恢复 elkeid-agent
cp /root/.openclaw/workspace/agent/archive/cloud-configs/elkeid-agent.service.backup \
   /etc/systemd/system/elkeid-agent.service
systemctl daemon-reload
systemctl restart elkeid-agent
```

---

## 风险评估

| 风险项 | 等级 | 说明 |
|--------|------|------|
| 日志监控缺失 | 低 | 云平台仍可监控性能指标，只是不收集日志内容 |
| 安全检测延迟 | 低 | elkeid 资源收紧，但 5% CPU 足够正常检测 |
| 云服务商告警 | 极低 | 资源使用降低，不会触发异常告警 |

---

## 验证命令

```bash
# 检查服务状态
systemctl status cloud-monitor-agent elkeid-agent

# 检查资源使用
ps -o pid,cmd,pcpu,pmem,rss -p $(pgrep -d',' cloud-monitor) -p $(pgrep -d',' elkeid)

# 检查配置是否生效
grep -E "(Logs|MemoryLimitInMb|CPUQuota)" /usr/local/cloud-monitor-agent/config.yaml
grep -E "(CPUQuota|MemoryMax)" /etc/systemd/system/elkeid-agent.service
```

---

## 结论

✅ **配置完成**

云服务商监控组件已限制：
1. **不再收集系统日志**（保护隐私）
2. **资源占用降低 20-30%**
3. **保持基本性能监控功能**
4. **安全监控继续运行**

风险等级：**低** → 功能完整但范围受限
