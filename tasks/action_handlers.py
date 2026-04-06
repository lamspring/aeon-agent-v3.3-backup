"""
Action Handlers - 任务动作处理器
为Worker提供具体的执行能力
"""

import os
import json
import subprocess
from typing import Dict, Any
from pathlib import Path

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from utils.structured_log import get_logger

logger = get_logger()


class ActionHandlers:
    """标准动作处理器"""
    
    @staticmethod
    def create_file(params: Dict[str, Any]) -> Dict[str, Any]:
        """创建文件"""
        path = params.get('path')
        content = params.get('content', '')
        
        if not path:
            raise ValueError("Missing 'path' parameter")
        
        # 确保目录存在
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"File created: {path}")
        
        return {
            "status": "success",
            "path": path,
            "bytes_written": len(content.encode('utf-8'))
        }
    
    @staticmethod
    def update_file(params: Dict[str, Any]) -> Dict[str, Any]:
        """更新文件"""
        path = params.get('path')
        content = params.get('content')
        mode = params.get('mode', 'overwrite')  # overwrite, append, prepend
        
        if not path:
            raise ValueError("Missing 'path' parameter")
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        
        if mode == 'overwrite':
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
        elif mode == 'append':
            with open(path, 'a', encoding='utf-8') as f:
                f.write(content)
        elif mode == 'prepend':
            with open(path, 'r', encoding='utf-8') as f:
                existing = f.read()
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content + existing)
        else:
            raise ValueError(f"Unknown mode: {mode}")
        
        logger.info(f"File updated: {path} (mode={mode})")
        
        return {
            "status": "success",
            "path": path,
            "mode": mode
        }
    
    @staticmethod
    def delete_file(params: Dict[str, Any]) -> Dict[str, Any]:
        """删除文件"""
        path = params.get('path')
        
        if not path:
            raise ValueError("Missing 'path' parameter")
        
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"File deleted: {path}")
            return {"status": "success", "path": path}
        else:
            return {"status": "skipped", "reason": "file_not_found", "path": path}
    
    @staticmethod
    def read_file(params: Dict[str, Any]) -> Dict[str, Any]:
        """读取文件"""
        path = params.get('path')
        limit = params.get('limit', None)  # 行数限制
        
        if not path:
            raise ValueError("Missing 'path' parameter")
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            if limit:
                lines = []
                for i, line in enumerate(f):
                    if i >= limit:
                        break
                    lines.append(line)
                content = ''.join(lines)
            else:
                content = f.read()
        
        return {
            "status": "success",
            "path": path,
            "content": content,
            "size": len(content)
        }
    
    @staticmethod
    def run_command(params: Dict[str, Any]) -> Dict[str, Any]:
        """运行命令"""
        command = params.get('command')
        cwd = params.get('cwd')
        timeout = params.get('timeout', 60)
        
        if not command:
            raise ValueError("Missing 'command' parameter")
        
        # 切换工作目录
        if cwd:
            original_cwd = os.getcwd()
            os.chdir(cwd)
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                "status": "success" if result.returncode == 0 else "error",
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command
            }
        finally:
            if cwd:
                os.chdir(original_cwd)
    
    @staticmethod
    def web_search(params: Dict[str, Any]) -> Dict[str, Any]:
        """网络搜索 (使用kimi_search)"""
        query = params.get('query')
        limit = params.get('limit', 5)
        
        if not query:
            raise ValueError("Missing 'query' parameter")
        
        # 这里可以集成实际的搜索API
        # 目前返回模拟结果
        logger.info(f"Web search: {query}")
        
        return {
            "status": "success",
            "query": query,
            "results": [],  # 实际实现需要调用搜索API
            "note": "Requires kimi_search integration"
        }
    
    @staticmethod
    def web_fetch(params: Dict[str, Any]) -> Dict[str, Any]:
        """获取网页内容 (使用kimi_fetch)"""
        url = params.get('url')
        
        if not url:
            raise ValueError("Missing 'url' parameter")
        
        logger.info(f"Web fetch: {url}")
        
        return {
            "status": "success",
            "url": url,
            "content": "",  # 实际实现需要调用fetch API
            "note": "Requires kimi_fetch integration"
        }
    
    @staticmethod
    def send_message(params: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        to = params.get('to')
        message = params.get('message')
        
        if not to or not message:
            raise ValueError("Missing 'to' or 'message' parameter")
        
        # 这里可以集成消息发送API
        logger.info(f"Message to {to}: {message[:50]}...")
        
        return {
            "status": "success",
            "to": to,
            "message_length": len(message)
        }
    
    @staticmethod
    def wait(params: Dict[str, Any]) -> Dict[str, Any]:
        """等待"""
        seconds = params.get('seconds', 1)
        
        import time
        time.sleep(seconds)
        
        return {
            "status": "success",
            "waited_seconds": seconds
        }
    
    @classmethod
    def get_handler(cls, action: str):
        """获取处理器"""
        handlers = {
            'create_file': cls.create_file,
            'update_file': cls.update_file,
            'delete_file': cls.delete_file,
            'read_file': cls.read_file,
            'run_command': cls.run_command,
            'web_search': cls.web_search,
            'web_fetch': cls.web_fetch,
            'send_message': cls.send_message,
            'wait': cls.wait,
        }
        
        return handlers.get(action)


def register_standard_handlers(worker):
    """注册标准处理器到Worker"""
    from tasks.task_system import Worker
    
    handlers = ActionHandlers()
    
    for action in ['create_file', 'update_file', 'delete_file', 'read_file',
                   'run_command', 'web_search', 'web_fetch', 'send_message', 'wait']:
        handler = ActionHandlers.get_handler(action)
        if handler:
            worker.register_handler(action, handler)
    
    logger.info("Standard handlers registered")
    
    return worker