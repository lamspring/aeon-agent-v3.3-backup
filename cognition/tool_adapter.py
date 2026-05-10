#!/usr/bin/env python3
"""
ToolAdapter - Aeon → OpenClaw 工具适配层 v1.0

将 OpenClaw 的 kimi_search, kimi_fetch, kimi_finance, browser, message 等工具
封装为 Aeon 可直接调用的接口。

核心设计:
- Aeon 决定"做什么"(goal)，ToolAdapter 负责"怎么做"(tool)
- 统一错误处理、超时、重试、限流
- 返回结构化结果，供 Aeon 认知循环消费

调用方式:
1. CLI 调用 (可靠，当前首选)
2. Gateway HTTP API (优雅，待验证)

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import subprocess
import json
import time
import shlex
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolResult:
    """工具调用统一结果格式"""
    success: bool
    tool: str
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    truncated: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "tool": self.tool,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
        }


class ToolAdapter:
    """
    OpenClaw 工具适配器
    
    可用工具清单:
    - search: kimi_search (网页搜索)
    - fetch: kimi_fetch (网页内容提取)
    - finance: kimi_finance (股票/金融数据)
    - browser: browser (浏览器自动化)
    - message: message (向用户发消息)
    - spawn: sessions_spawn (子代理)
    - tts: tts (语音合成)
    """
    
    TOOLS = {
        "search": {
            "description": "搜索互联网获取最新信息",
            "params": ["query", "count", "freshness", "language"],
            "required": ["query"],
        },
        "fetch": {
            "description": "抓取网页内容",
            "params": ["url", "extractMode", "maxChars"],
            "required": ["url"],
        },
        "finance": {
            "description": "获取股票行情数据",
            "params": ["ticker", "type", "time", "file_path"],
            "required": ["ticker", "file_path"],
        },
        "message": {
            "description": "向用户发送消息",
            "params": ["message", "channel", "media"],
            "required": ["message"],
        },
        "spawn": {
            "description": "启动子代理执行复杂任务",
            "params": ["task", "model", "timeoutSeconds"],
            "required": ["task"],
        },
        "mimo_tts": {
            "description": "小米MiMo TTS语音合成（虾虾专属音色）",
            "params": ["text", "voice", "style", "output_path"],
            "required": ["text"],
        },
    }
    
    def __init__(self, timeout: int = 30, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries
        self._stats = {
            "calls": 0,
            "successes": 0,
            "failures": 0,
            "by_tool": {},
        }
    
    def list_tools(self) -> Dict[str, Dict]:
        """返回可用工具清单"""
        return self.TOOLS
    
    def can_handle(self, action: str) -> bool:
        """检查是否能处理某个 action"""
        return action in self.TOOLS
    
    def call(self, tool_name: str, params: Dict[str, Any]) -> ToolResult:
        """
        调用指定工具
        
        Args:
            tool_name: 工具名 (search/fetch/finance/message/...)
            params: 工具参数
        
        Returns:
            ToolResult: 统一结果格式
        """
        start = time.time()
        self._stats["calls"] += 1
        
        if tool_name not in self.TOOLS:
            return ToolResult(
                success=False,
                tool=tool_name,
                error=f"Unknown tool: {tool_name}. Available: {list(self.TOOLS.keys())}"
            )
        
        # 检查必需参数
        required = self.TOOLS[tool_name].get("required", [])
        missing = [p for p in required if p not in params or params[p] is None]
        if missing:
            return ToolResult(
                success=False,
                tool=tool_name,
                error=f"Missing required params: {missing}"
            )
        
        # 执行工具调用
        method = getattr(self, f"_call_{tool_name}", None)
        if not method:
            return ToolResult(
                success=False,
                tool=tool_name,
                error=f"Tool '{tool_name}' not implemented yet"
            )
        
        # 重试逻辑
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                result = method(params)
                result.duration_ms = (time.time() - start) * 1000
                if result.success:
                    self._stats["successes"] += 1
                else:
                    self._stats["failures"] += 1
                self._track(tool_name, result.success)
                return result
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(1)
                    continue
        
        # 所有重试失败
        result = ToolResult(
            success=False,
            tool=tool_name,
            error=f"All {self.max_retries + 1} attempts failed. Last: {last_error}"
        )
        result.duration_ms = (time.time() - start) * 1000
        self._stats["failures"] += 1
        self._track(tool_name, False)
        return result
    
    def _track(self, tool: str, success: bool):
        """统计追踪"""
        if tool not in self._stats["by_tool"]:
            self._stats["by_tool"][tool] = {"calls": 0, "successes": 0}
        self._stats["by_tool"][tool]["calls"] += 1
        if success:
            self._stats["by_tool"][tool]["successes"] += 1
    
    def get_stats(self) -> Dict:
        """获取工具调用统计"""
        return self._stats.copy()
    
    # ============== 具体工具实现 ==============
    
    def _call_search(self, params: Dict) -> ToolResult:
        """调用 kimi_search"""
        query = params["query"]
        count = params.get("count", 5)
        freshness = params.get("freshness", "")
        language = params.get("language", "zh")
        
        # 构建 CLI 参数
        args = ["openclaw", "search", query, "--count", str(count)]
        if freshness:
            args.extend(["--freshness", freshness])
        if language:
            args.extend(["--language", language])
        
        return self._run_cli(args, "search")
    
    def _call_fetch(self, params: Dict) -> ToolResult:
        """调用 kimi_fetch"""
        url = params["url"]
        extract_mode = params.get("extractMode", "markdown")
        max_chars = params.get("maxChars", 50000)
        
        args = ["openclaw", "fetch", url, "--extract-mode", extract_mode]
        if max_chars:
            args.extend(["--max-chars", str(max_chars)])
        
        return self._run_cli(args, "fetch")
    
    def _call_finance(self, params: Dict) -> ToolResult:
        """调用 kimi_finance"""
        ticker = params["ticker"]
        data_type = params.get("type", "realtime_price")
        time_str = params.get("time", "")
        file_path = params.get("file_path", f"/tmp/finance_{ticker.replace('.', '_')}.csv")
        
        args = [
            "openclaw", "finance",
            ticker,
            "--type", data_type,
            "--file-path", file_path,
        ]
        if time_str:
            args.extend(["--time", time_str])
        
        return self._run_cli(args, "finance")
    
    def _call_message(self, params: Dict) -> ToolResult:
        """
        调用 message 向用户发消息
        
        重要: 这是 Aeon 主动通信的通道
        参数:
            message: 消息内容
            channel: 渠道 (openclaw-weixin|feishu|discord|...)
            media: 媒体文件路径 (可选)
            target: 目标用户ID (可选，默认朋朋的微信)
        """
        message_text = params["message"]
        channel = params.get("channel", "openclaw-weixin")
        media = params.get("media", "")
        # 默认发给朋朋的微信
        target = params.get("target", "o9cq806JQxsn4CVsKFpl4wX-kCr8@im.wechat")
        
        args = ["openclaw", "message", "send", "--target", target, "--message", message_text]
        if channel:
            args.extend(["--channel", channel])
        if media:
            args.extend(["--media", media])
        
        return self._run_cli(args, "message")
    
    def _call_spawn(self, params: Dict) -> ToolResult:
        """调用 sessions_spawn 启动子代理"""
        task = params["task"]
        model = params.get("model", "kimi-coding/k2.6")
        timeout = params.get("timeoutSeconds", 300)
        
        # sessions_spawn 通过 sessions_spawn CLI 不存在
        # 需要通过 openclaw sessions-spawn 或者 HTTP API
        # 当前使用 exec 调用
        
        args = [
            "openclaw", "sessions-spawn",
            "--task", task,
            "--model", model,
            "--timeout-seconds", str(timeout),
        ]
        
        return self._run_cli(args, "spawn")
    
    def _call_tts(self, params: Dict) -> ToolResult:
        """调用 tts 文字转语音"""
        text = params["text"]
        channel = params.get("channel", "")
        
        args = ["openclaw", "tts", text]
        if channel:
            args.extend(["--channel", channel])
        
        return self._run_cli(args, "tts")

    def _call_mimo_tts(self, params: Dict) -> ToolResult:
        """
        调用 MiMo TTS 生成语音
        
        参数:
            text: 要合成的文本
            voice: 音色（冰糖/茉莉/苏打/白桦/Mia/Chloe/Milo/Dean）
            style: 语气风格描述
            output_path: 输出文件路径
        
        默认使用虾虾专属配置
        """
        import urllib.request, json, base64
        
        text = params.get("text", "")
        voice = params.get("voice", "冰糖")
        style = params.get("style", "轻快、活泼、带点俏皮的语气，像朋友聊天一样自然亲切")
        output_path = params.get("output_path", "/tmp/mimo_tts_output.wav")
        
        # 虾虾专属音色配置
        if voice == "虾虾":
            voice = "冰糖"
            style = "轻快活泼的语气，像弹幕区最会接话的网友朋友，语速适中偏快，咬字清晰自然，尾音带着一点俏皮上扬"
        
        api_key = "tp-c80alurd96kqx0acohglgeyzxeryn0tukzd6wrc5uit9k9hl"
        
        payload = {
            "model": "mimo-v2.5-tts",
            "messages": [
                {
                    "role": "user",
                    "content": style
                },
                {
                    "role": "assistant",
                    "content": text
                }
            ],
            "audio": {
                "format": "wav",
                "voice": voice
            }
        }
        
        try:
            req = urllib.request.Request(
                "https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                msg = data["choices"][0]["message"]
                
                if "audio" in msg:
                    audio_data = msg["audio"]
                    if isinstance(audio_data, dict) and "data" in audio_data:
                        audio_bytes = base64.b64decode(audio_data["data"])
                        with open(output_path, "wb") as f:
                            f.write(audio_bytes)
                        
                        return ToolResult(
                            success=True,
                            tool="mimo_tts",
                            data={
                                "file_path": output_path,
                                "size_bytes": len(audio_bytes),
                                "voice": voice,
                                "text": text
                            }
                        )
                
                return ToolResult(
                    success=False,
                    tool="mimo_tts",
                    error="No audio data in response"
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                tool="mimo_tts",
                error=str(e)[:200]
            )
    
    def _run_cli(self, args: List[str], tool_name: str) -> ToolResult:
        """
        通过 CLI 执行工具调用
        
        注意: openclaw CLI 可能不支持所有工具，需要逐步验证
        如果 CLI 不支持，fallback 到直接 Python 调用
        """
        try:
            # 先尝试 CLI
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd="/root/.openclaw/workspace"
            )
            
            if result.returncode == 0:
                # 尝试解析 JSON 输出
                try:
                    data = json.loads(result.stdout)
                    return ToolResult(success=True, tool=tool_name, data=data)
                except json.JSONDecodeError:
                    # 非 JSON 输出，作为文本返回
                    return ToolResult(
                        success=True,
                        tool=tool_name,
                        data={"raw_output": result.stdout[:2000], "truncated": len(result.stdout) > 2000}
                    )
            else:
                error = result.stderr or result.stdout or "Unknown CLI error"
                return ToolResult(
                    success=False,
                    tool=tool_name,
                    error=f"CLI exit code {result.returncode}: {error[:500]}"
                )
                
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                tool=tool_name,
                error=f"Timeout after {self.timeout}s"
            )
        except FileNotFoundError:
            # openclaw CLI 不存在，fallback
            return ToolResult(
                success=False,
                tool=tool_name,
                error="openclaw CLI not found"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                tool=tool_name,
                error=f"Exception: {str(e)[:500]}"
            )
    
    # ============== 高级封装 ==============
    
    def research(self, topic: str, depth: int = 1) -> ToolResult:
        """
        研究模式: 搜索 → 抓取 → 汇总
        
        Args:
            topic: 研究主题
            depth: 抓取前 N 个结果深入分析 (1-3)
        
        Returns:
            ToolResult: {summaries: [...], sources: [...]}
        """
        # Step 1: 搜索
        search_result = self.call("search", {"query": topic, "count": depth * 3})
        if not search_result.success:
            return search_result
        
        # Step 2: 抓取关键结果
        summaries = []
        sources = []
        
        results = search_result.data.get("results", search_result.data.get("raw_output", []))
        if isinstance(results, str):
            # 解析文本输出
            return ToolResult(
                success=True,
                tool="research",
                data={"search_results": results, "depth": depth}
            )
        
        # 如果是结构化结果，抓取每个 URL
        if isinstance(results, list):
            for item in results[:depth]:
                url = item.get("url") if isinstance(item, dict) else str(item)
                if url and url.startswith("http"):
                    fetch_result = self.call("fetch", {"url": url, "maxChars": 10000})
                    if fetch_result.success:
                        content = fetch_result.data.get("content", fetch_result.data.get("raw_output", ""))
                        summaries.append({
                            "url": url,
                            "title": item.get("title", "Unknown"),
                            "summary": content[:500] if isinstance(content, str) else str(content)[:500]
                        })
                        sources.append(url)
        
        return ToolResult(
            success=True,
            tool="research",
            data={
                "topic": topic,
                "depth": depth,
                "summaries": summaries,
                "sources": sources,
                "search_raw": search_result.data,
            }
        )
    
    def notify(self, message: str, channel: str = "openclaw-weixin", priority: str = "normal") -> ToolResult:
        """
        通知用户 (Aeon 主动通信)
        
        Args:
            message: 消息内容
            channel: 渠道
            priority: normal/urgent/low
        
        使用场景:
        - 每日报告
        - 紧急事件
        - 目标完成通知
        - 好奇心触发发现
        """
        # 高优先级加前缀
        if priority == "urgent":
            message = f"🚨 [紧急] {message}"
        elif priority == "low":
            message = f"💤 {message}"
        
        return self.call("message", {
            "message": message,
            "channel": channel,
        })
    
    def monitor_stock(self, ticker: str, alert_threshold: float = 0.05) -> ToolResult:
        """
        监控股票 (封装 finance + 趋势判断)
        
        Args:
            ticker: 股票代码
            alert_threshold: 涨跌幅 alerting 阈值 (0.05 = 5%)
        """
        import datetime
        
        now = datetime.datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:00")
        file_path = f"/tmp/stock_{ticker.replace('.', '_')}_{now.strftime('%Y%m%d')}.csv"
        
        result = self.call("finance", {
            "ticker": ticker,
            "type": "realtime_price",
            "time": time_str,
            "file_path": file_path,
        })
        
        if not result.success:
            return result
        
        # 读取 CSV 分析
        try:
            import csv
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                if rows:
                    latest = rows[-1]
                    pct_chg = float(latest.get('pct_chg', 0))
                    
                    alert = abs(pct_chg) >= alert_threshold * 100
                    
                    return ToolResult(
                        success=True,
                        tool="monitor_stock",
                        data={
                            "ticker": ticker,
                            "price": latest.get('close'),
                            "change_pct": pct_chg,
                            "alert": alert,
                            "alert_reason": f"涨跌幅 {pct_chg:.2f}% 超过阈值 {alert_threshold*100:.1f}%" if alert else None,
                            "raw": rows,
                        }
                    )
        except Exception as e:
            return ToolResult(
                success=True,
                tool="monitor_stock",
                data={"raw_file": file_path, "parse_error": str(e)}
            )
        
        return result


# ============== 快速测试 ==============
if __name__ == "__main__":
    adapter = ToolAdapter(timeout=30)
    
    print("=== ToolAdapter v1.0 - 可用工具清单 ===")
    for name, info in adapter.list_tools().items():
        print(f"  {name}: {info['description']}")
        print(f"    params: {info['params']}")
        print(f"    required: {info['required']}")
    
    print(f"\n=== 统计 ===")
    print(adapter.get_stats())
