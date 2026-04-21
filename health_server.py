#!/usr/bin/env python3
"""
Aeon Health HTTP Server - 健康检查端点

提供:
- GET /health - 健康状态
- GET /metrics - Prometheus 格式指标
- GET /api/status - JSON 系统状态
- GET /api/goals - 目标列表

Usage:
    python3 health_server.py --port 8080
"""

import sys
import json
import argparse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, '/root/.openclaw/workspace/agent')

from goals import GoalManager
from bus.event_bus_v2 import get_event_bus
from cognition.cognition_loop import get_cognition


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""
    
    def log_message(self, format, *args):
        """静默日志（可选开启）"""
        pass
    
    def _send_json(self, data: Dict[str, Any], status: int = 200):
        """发送 JSON 响应"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def _send_text(self, text: str, status: int = 200):
        """发送纯文本响应"""
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(text.encode())
    
    def do_GET(self):
        """处理 GET 请求"""
        path = self.path
        
        if path == '/health':
            self._handle_health()
        elif path == '/metrics':
            self._handle_metrics()
        elif path == '/api/status':
            self._handle_api_status()
        elif path == '/api/goals':
            self._handle_api_goals()
        elif path == '/api/events':
            self._handle_api_events()
        elif path == '/':
            self._handle_index()
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def _handle_health(self):
        """健康检查端点"""
        try:
            gm = GoalManager()
            bus = get_event_bus()
            
            # 基础健康检查
            healthy = True
            checks = {
                "goals_db": True,
                "event_bus": True,
                "queue_size": bus.get_queue_size(),
            }
            
            # 队列堆积告警
            if checks["queue_size"] > 100:
                checks["warning"] = "High event queue"
                healthy = False
            
            status = "healthy" if healthy else "degraded"
            
            self._send_json({
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "checks": checks
            })
            
        except Exception as e:
            self._send_json({
                "status": "unhealthy",
                "error": str(e)
            }, 503)
    
    def _handle_metrics(self):
        """Prometheus 格式指标"""
        try:
            gm = GoalManager()
            bus = get_event_bus()
            
            stats = gm.get_statistics()
            queue_size = bus.get_queue_size()
            
            # Prometheus 格式
            metrics = f"""# HELP aeon_goals_total Total number of goals
# TYPE aeon_goals_total gauge
aeon_goals_total{{status="pending"}} {stats.get('pending', 0)}
aeon_goals_total{{status="active"}} {stats.get('active', 0)}
aeon_goals_total{{status="completed"}} {stats.get('completed', 0)}
aeon_goals_total{{status="failed"}} {stats.get('failed', 0)}

# HELP aeon_events_queue_size Current event queue size
# TYPE aeon_events_queue_size gauge
aeon_events_queue_size {queue_size}

# HELP aeon_up Aeon agent is up
# TYPE aeon_up gauge
aeon_up 1
"""
            self._send_text(metrics)
            
        except Exception as e:
            self._send_text(f"# Error: {e}", 500)
    
    def _handle_api_status(self):
        """完整系统状态 API"""
        try:
            gm = GoalManager()
            bus = get_event_bus()
            cognition = get_cognition()
            
            goal_stats = gm.get_statistics()
            active_goal = gm.get_active_goal()
            
            status = {
                "version": "3.3",
                "timestamp": datetime.now().isoformat(),
                "goals": {
                    "statistics": goal_stats,
                    "active": active_goal.to_dict() if active_goal else None,
                },
                "events": {
                    "queue_size": bus.get_queue_size(),
                    "worker_id": bus.worker_id,
                },
                "cognition": cognition.get_status(),
            }
            
            self._send_json(status)
            
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
    
    def _handle_api_goals(self):
        """目标列表 API"""
        try:
            gm = GoalManager()
            goals = gm.list_goals()
            
            result = [g.to_dict() for g in goals]
            self._send_json({"goals": result, "count": len(result)})
            
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
    
    def _handle_api_events(self):
        """事件队列 API"""
        try:
            bus = get_event_bus()
            events = bus.get_pending_events(limit=50)
            
            self._send_json({
                "queue_size": bus.get_queue_size(),
                "events": events
            })
            
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
    
    def _handle_index(self):
        """根路径 - API 文档"""
        doc = {
            "service": "Aeon Agent Health API",
            "version": "3.3",
            "endpoints": {
                "/health": "Health check (JSON)",
                "/metrics": "Prometheus metrics (text)",
                "/api/status": "Full system status (JSON)",
                "/api/goals": "Goals list (JSON)",
                "/api/events": "Event queue (JSON)",
            }
        }
        self._send_json(doc)


class HealthServer:
    """健康检查服务器"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = int(port)  # 确保是整数
        self.server = None
        self.thread = None
        self._running = False
    
    def start(self):
        """启动服务器（后台线程）"""
        self.server = HTTPServer((self.host, self.port), HealthHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._running = True
        print(f"Health server started on http://{self.host}:{self.port}")
    
    def stop(self):
        """停止服务器"""
        if self.server:
            self.server.shutdown()
            self._running = False
            print("Health server stopped")
    
    def is_running(self) -> bool:
        return self._running


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Aeon Health HTTP Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind')
    args = parser.parse_args()
    
    server = HealthServer(host=args.host, port=args.port)
    server.start()
    
    try:
        print(f"\nHealth API available at:")
        print(f"  http://localhost:{args.port}/health")
        print(f"  http://localhost:{args.port}/metrics")
        print(f"  http://localhost:{args.port}/api/status")
        print(f"\nPress Ctrl+C to stop\n")
        
        # 保持运行
        while True:
            import time
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
        server.stop()


if __name__ == '__main__':
    main()
