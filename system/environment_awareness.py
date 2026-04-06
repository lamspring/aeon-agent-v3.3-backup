#!/usr/bin/env python3
"""
Environment Awareness - 环境感知模块

感知Agent运行环境的各种状态：
  - 系统资源 (CPU、内存、磁盘)
  - 网络状态
  - 文件系统变化
  - 时间上下文
  - 工作区状态
"""
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR))

def log_simple(msg):
    """简化日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = AGENT_DIR / "logs" / "execution_log.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] [ENV] {msg}\n")

class EnvironmentAwareness:
    """环境感知模块"""
    
    def __init__(self):
        self.config = self._load_config()
        self.last_state = {}
    
    def _load_config(self):
        """加载配置"""
        config_path = AGENT_DIR / "system" / "environment_config.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # ============================================
    # 传感器: 系统资源
    # ============================================
    def _get_system_resources(self):
        """获取系统资源使用情况"""
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
            
            return {
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory.percent, 1),
                "memory_available_mb": round(memory.available / 1024 / 1024, 0),
                "disk_percent": round(disk.percent, 1),
                "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
                "load_average": [round(x, 2) for x in load_avg],
                "timestamp": datetime.now().isoformat()
            }
        except ImportError:
            # 如果没有psutil，使用基础命令
            try:
                # 内存
                mem_info = subprocess.run(['free', '-m'], capture_output=True, text=True)
                # CPU负载
                load = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
                # 磁盘
                disk_info = subprocess.run(['df', '-h', '/'], capture_output=True, text=True)
                
                return {
                    "cpu_percent": None,
                    "memory_info": mem_info.stdout if mem_info.returncode == 0 else "N/A",
                    "disk_info": disk_info.stdout if disk_info.returncode == 0 else "N/A",
                    "load_average": [round(x, 2) for x in load],
                    "timestamp": datetime.now().isoformat()
                }
            except:
                return {"error": "无法获取系统资源", "timestamp": datetime.now().isoformat()}
    
    # ============================================
    # 传感器: 网络状态
    # ============================================
    def _get_network_status(self):
        """获取网络状态"""
        try:
            # 检查网络连通性
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '2', '8.8.8.8'],
                capture_output=True,
                text=True
            )
            is_connected = result.returncode == 0
            
            # 如果连通，获取延迟
            latency = None
            if is_connected and 'time=' in result.stdout:
                try:
                    time_part = result.stdout.split('time=')[1].split()[0]
                    latency = float(time_part.replace('ms', ''))
                except:
                    pass
            
            return {
                "is_connected": is_connected,
                "latency_ms": round(latency, 1) if latency else None,
                "timestamp": datetime.now().isoformat()
            }
        except:
            return {"is_connected": False, "error": "检查失败", "timestamp": datetime.now().isoformat()}
    
    # ============================================
    # 传感器: 文件系统
    # ============================================
    def _get_filesystem_state(self):
        """获取文件系统状态"""
        states = {}
        
        for path_str in self.config.get("sensors", {}).get("filesystem", {}).get("watch_paths", []):
            path = Path(path_str)
            if path.exists():
                try:
                    # 统计文件数
                    file_count = sum(1 for _ in path.rglob('*') if _.is_file())
                    # 统计目录数
                    dir_count = sum(1 for _ in path.rglob('*') if _.is_dir())
                    # 总大小
                    total_size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                    
                    states[path_str] = {
                        "file_count": file_count,
                        "dir_count": dir_count,
                        "total_size_mb": round(total_size / 1024 / 1024, 2),
                        "exists": True
                    }
                except Exception as e:
                    states[path_str] = {"exists": True, "error": str(e)}
            else:
                states[path_str] = {"exists": False}
        
        return states
    
    # ============================================
    # 传感器: 时间上下文
    # ============================================
    def _get_time_context(self):
        """获取时间上下文"""
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()  # 0=周一, 6=周日
        
        return {
            "timestamp": now.isoformat(),
            "hour": hour,
            "day_of_week": weekday,
            "day_name": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday],
            "is_weekend": weekday >= 5,
            "is_working_hours": 9 <= hour < 18,
            "is_night": hour >= 23 or hour < 6,
            "is_early_morning": 2 <= hour < 4  # 服务器重启时段
        }
    
    # ============================================
    # 传感器: 工作区状态
    # ============================================
    def _get_workspace_state(self):
        """获取工作区状态"""
        state = {
            "workspace_path": str(AGENT_DIR),
            "timestamp": datetime.now().isoformat()
        }
        
        # Git状态
        if self.config.get("sensors", {}).get("workspace_state", {}).get("track_git_status", True):
            try:
                git_status = subprocess.run(
                    ['git', '-C', str(AGENT_DIR), 'status', '--porcelain'],
                    capture_output=True,
                    text=True
                )
                if git_status.returncode == 0:
                    changes = git_status.stdout.strip().split('\n') if git_status.stdout.strip() else []
                    state["git_changes"] = len([c for c in changes if c.strip()])
                    state["has_uncommitted_changes"] = state["git_changes"] > 0
            except:
                state["git_available"] = False
        
        # 文件统计
        if self.config.get("sensors", {}).get("workspace_state", {}).get("count_files", True):
            try:
                py_files = list(AGENT_DIR.rglob('*.py'))
                json_files = list(AGENT_DIR.rglob('*.json'))
                md_files = list(AGENT_DIR.rglob('*.md'))
                
                state["file_counts"] = {
                    "python": len(py_files),
                    "json": len(json_files),
                    "markdown": len(md_files),
                    "total": len(py_files) + len(json_files) + len(md_files)
                }
            except:
                pass
        
        # 最近修改
        if self.config.get("sensors", {}).get("workspace_state", {}).get("check_recent_changes", True):
            try:
                # 获取最近10分钟的修改
                ten_min_ago = datetime.now().timestamp() - 600
                recent_files = []
                
                for f in AGENT_DIR.rglob('*'):
                    if f.is_file() and f.stat().st_mtime > ten_min_ago:
                        recent_files.append({
                            "path": str(f.relative_to(AGENT_DIR)),
                            "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                        })
                
                state["recent_changes"] = recent_files[:10]  # 最多10个
            except:
                pass
        
        return state
    
    # ============================================
    # 检查警报
    # ============================================
    def _check_alerts(self, resources):
        """检查是否需要警报"""
        alerts = []
        thresholds = self.config.get("alerts", {})
        
        if resources.get("cpu_percent", 0) > thresholds.get("high_cpu_threshold", 80):
            alerts.append(f"⚠️ CPU使用率过高: {resources['cpu_percent']}%")
        
        if resources.get("memory_percent", 0) > thresholds.get("high_memory_threshold", 85):
            alerts.append(f"⚠️ 内存使用率过高: {resources['memory_percent']}%")
        
        if resources.get("disk_percent", 0) > (100 - thresholds.get("low_disk_threshold", 10)):
            alerts.append(f"⚠️ 磁盘空间不足: 仅剩{100 - resources['disk_percent']}%")
        
        load = resources.get("load_average", [0, 0, 0])
        if load and load[0] > thresholds.get("max_load_average", 4.0):
            alerts.append(f"⚠️ 系统负载过高: {load[0]}")
        
        return alerts
    
    # ============================================
    # 主接口
    # ============================================
    def perceive(self):
        """
        感知环境 - 主接口
        
        Returns:
            dict: 完整的环境状态
        """
        if not self.config.get("enabled", True):
            return {"enabled": False}
        
        state = {
            "timestamp": datetime.now().isoformat(),
            "sensors": {}
        }
        
        # 收集各传感器数据
        sensors_config = self.config.get("sensors", {})
        
        if sensors_config.get("system_resources", {}).get("enabled", True):
            state["sensors"]["system_resources"] = self._get_system_resources()
        
        if sensors_config.get("network", {}).get("enabled", True):
            state["sensors"]["network"] = self._get_network_status()
        
        if sensors_config.get("filesystem", {}).get("enabled", True):
            state["sensors"]["filesystem"] = self._get_filesystem_state()
        
        if sensors_config.get("time_context", {}).get("enabled", True):
            state["sensors"]["time_context"] = self._get_time_context()
        
        if sensors_config.get("workspace_state", {}).get("enabled", True):
            state["sensors"]["workspace_state"] = self._get_workspace_state()
        
        # 检查警报
        if "system_resources" in state["sensors"]:
            state["alerts"] = self._check_alerts(state["sensors"]["system_resources"])
        
        # 记录到日志
        if self.config.get("logging", {}).get("log_to_file", True):
            log_simple(f"Environment scan: CPU={state['sensors'].get('system_resources', {}).get('cpu_percent', 'N/A')}%, " +
                      f"Memory={state['sensors'].get('system_resources', {}).get('memory_percent', 'N/A')}%, " +
                      f"Files={state['sensors'].get('workspace_state', {}).get('file_counts', {}).get('total', 'N/A')}")
        
        self.last_state = state
        return state
    
    def get_summary(self):
        """获取环境摘要"""
        state = self.perceive()
        
        time_ctx = state.get("sensors", {}).get("time_context", {})
        resources = state.get("sensors", {}).get("system_resources", {})
        network = state.get("sensors", {}).get("network", {})
        workspace = state.get("sensors", {}).get("workspace_state", {})
        
        summary_parts = []
        
        # 时间
        if time_ctx:
            summary_parts.append(f"🕐 {time_ctx.get('day_name')} {time_ctx.get('hour'):02d}:00")
            if time_ctx.get('is_early_morning'):
                summary_parts.append("⚠️ 服务器重启时段")
        
        # 资源
        if resources:
            summary_parts.append(f"💻 CPU:{resources.get('cpu_percent', '?')}% Mem:{resources.get('memory_percent', '?')}%")
        
        # 网络
        if network:
            net_status = "🌐 在线" if network.get('is_connected') else "❌ 离线"
            if network.get('latency_ms'):
                net_status += f" ({network['latency_ms']}ms)"
            summary_parts.append(net_status)
        
        # 工作区
        if workspace and workspace.get('file_counts'):
            summary_parts.append(f"📁 {workspace['file_counts'].get('total', '?')} files")
        
        return " | ".join(summary_parts)

if __name__ == "__main__":
    print("=== Environment Awareness Test ===\n")
    
    env = EnvironmentAwareness()
    state = env.perceive()
    
    print("🌍 环境感知结果:\n")
    print(json.dumps(state, indent=2, ensure_ascii=False))
    
    print("\n" + "="*50)
    print("\n📋 摘要:")
    print(env.get_summary())
    
    if state.get("alerts"):
        print("\n⚠️ 警报:")
        for alert in state["alerts"]:
            print(f"  {alert}")
