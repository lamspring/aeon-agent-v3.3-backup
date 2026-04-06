"""
Task Planner - 任务规划器
核心特性:
- LLM 规划任务列表
- Pydantic Schema 强制校验
- Plan Cache (1小时缓存)
- 依赖管理
"""

import json
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from pydantic import BaseModel, Field, validator
from enum import Enum
import logging

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from bus.event_bus import get_event_bus, EventType, listener
from utils.structured_log import get_logger, LogContext
from tasks.task_system import TaskQueue, Task, TaskStatus

logger = get_logger()


class ActionType(Enum):
    """标准动作类型"""
    CREATE_FILE = "create_file"
    UPDATE_FILE = "update_file"
    DELETE_FILE = "delete_file"
    RUN_COMMAND = "run_command"
    READ_FILE = "read_file"
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    SEND_MESSAGE = "send_message"
    CREATE_TASK = "create_task"
    WAIT = "wait"


class TaskDefinition(BaseModel):
    """
    任务定义 Schema
    
    严格的结构化输出，Worker可稳定执行
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    action: str = Field(
        ..., 
        description="动作类型",
        examples=["create_file", "run_command", "web_search"]
    )
    params: Dict[str, Any] = Field(
        ..., 
        description="动作参数"
    )
    description: str = Field(
        ..., 
        description="人类可读的任务描述"
    )
    
    # 执行控制
    retry: int = Field(
        default=3, 
        ge=0, 
        le=5, 
        description="失败时的重试次数"
    )
    timeout: int = Field(
        default=120, 
        ge=10, 
        le=3600, 
        description="超时时间(秒)"
    )
    
    # 依赖
    depends_on: Optional[List[str]] = Field(
        default=None, 
        description="依赖的任务ID列表"
    )
    
    # 回调
    on_success: Optional[str] = Field(
        default=None, 
        description="成功后的下一个任务ID"
    )
    on_failure: Optional[str] = Field(
        default=None, 
        description="失败后的处理策略: retry|skip|abort"
    )
    
    @validator('action')
    def validate_action(cls, v):
        """验证动作类型"""
        allowed = [
            "create_file", "update_file", "delete_file",
            "run_command", "read_file",
            "web_search", "web_fetch",
            "send_message", "create_task",
            "wait", "unknown"
        ]
        if v not in allowed:
            raise ValueError(f"Unknown action: {v}. Allowed: {allowed}")
        return v
    
    @validator('on_failure')
    def validate_on_failure(cls, v):
        """验证失败处理策略"""
        if v and v not in ['retry', 'skip', 'abort']:
            raise ValueError(f"Invalid on_failure: {v}. Must be retry|skip|abort")
        return v


class PlanOutput(BaseModel):
    """
    规划输出 Schema
    
    LLM必须按此格式输出
    """
    goal: str = Field(
        ..., 
        description="原始目标描述"
    )
    tasks: List[TaskDefinition] = Field(
        ..., 
        description="任务列表",
        min_items=1
    )
    estimated_time: int = Field(
        ..., 
        ge=1, 
        le=480,  # 最多8小时
        description="预计总时间(分钟)"
    )
    reasoning: str = Field(
        default="",
        description="规划理由和思路"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "goal": "完成v30架构升级",
                "tasks": [
                    {
                        "id": "task_001",
                        "action": "create_file",
                        "params": {
                            "path": "agent/bus/event_bus.py",
                            "content": "# Event Bus implementation..."
                        },
                        "description": "创建Event Bus基础模块",
                        "retry": 3,
                        "timeout": 120
                    },
                    {
                        "id": "task_002", 
                        "action": "run_command",
                        "params": {
                            "command": "python3 -m pytest tests/",
                            "cwd": "agent/bus"
                        },
                        "description": "运行测试验证",
                        "retry": 2,
                        "timeout": 300,
                        "depends_on": ["task_001"],
                        "on_failure": "abort"
                    }
                ],
                "estimated_time": 30,
                "reasoning": "先创建核心模块，再运行测试验证"
            }
        }


class TaskPlanner:
    """
    任务规划器
    
    职责:
    - 监听 cognition.plan 事件
    - 调用LLM生成任务列表
    - Schema校验
    - 加入Task Queue
    """
    
    def __init__(self, llm_client: Optional[Callable] = None):
        self.event_bus = get_event_bus()
        self.logger = get_logger()
        self.task_queue = TaskQueue()
        self.llm_client = llm_client
        
        # 订阅规划事件
        self._subscribe()
    
    def _subscribe(self):
        """订阅规划事件"""
        @listener(EventType.COGNITION_PLAN.value)
        def on_plan(event):
            self._handle_plan_event(event)
    
    def _handle_plan_event(self, event):
        """处理规划事件"""
        data = event.data
        goal = data.get('goal')
        plan_id = data.get('plan_id')
        trace_id = event.trace_id
        
        if not goal:
            self.logger.warning(
                "Plan event missing goal",
                event_id=event.event_id,
                trace_id=trace_id
            )
            return
        
        self.logger.info(
            f"Planning tasks for: {goal[:50]}...",
            trace_id=trace_id,
            component="TaskPlanner"
        )
        
        # 生成任务列表
        plan = self.plan(goal)
        
        if plan:
            # 加入队列
            self._enqueue_tasks(plan, trace_id)
        else:
            self.logger.error(
                f"Planning failed for: {goal[:50]}...",
                trace_id=trace_id
            )
    
    def plan(self, goal: str) -> Optional[PlanOutput]:
        """
        规划任务
        
        流程:
        1. 构建prompt
        2. 调用LLM
        3. Schema校验
        4. 返回PlanOutput
        """
        if not self.llm_client:
            self.logger.warning("No LLM client configured")
            return None
        
        # 构建prompt
        prompt = self._build_prompt(goal)
        
        try:
            # 调用LLM
            raw_output = self.llm_client(prompt)
            
            # 解析JSON
            data = json.loads(raw_output)
            
            # Schema校验
            plan = PlanOutput(**data)
            
            self.logger.info(
                f"Plan generated: {len(plan.tasks)} tasks",
                component="TaskPlanner",
                context={"goal": goal[:50], "tasks": len(plan.tasks)}
            )
            
            return plan
            
        except json.JSONDecodeError as e:
            self.logger.error(
                f"LLM output is not valid JSON: {e}",
                component="TaskPlanner"
            )
            return None
            
        except Exception as e:
            self.logger.error(
                f"Plan validation failed: {e}",
                component="TaskPlanner"
            )
            return None
    
    def _build_prompt(self, goal: str) -> str:
        """构建规划prompt"""
        
        schema_example = json.dumps(PlanOutput.Config.schema_extra["example"], indent=2)
        
        prompt = f"""你是一个任务规划助手。请将以下目标分解为可执行的任务列表。

目标: {goal}

要求:
1. 将目标分解为 1-10 个具体任务
2. 每个任务必须包含 action, params, description
3. 如果任务之间有依赖关系，使用 depends_on 指定
4. action 必须是以下之一:
   - create_file: 创建文件 (params: path, content)
   - update_file: 更新文件 (params: path, content, mode)
   - delete_file: 删除文件 (params: path)
   - run_command: 运行命令 (params: command, cwd)
   - read_file: 读取文件 (params: path)
   - web_search: 搜索 (params: query)
   - web_fetch: 获取网页 (params: url)
   - send_message: 发送消息 (params: to, message)
   - wait: 等待 (params: seconds)
5. 合理设置 retry (0-5) 和 timeout (10-3600秒)
6. 预估总时间 estimated_time (分钟)

输出格式 (必须严格遵循JSON Schema):
```json
{schema_example}
```

请只输出JSON，不要其他内容。"""

        return prompt
    
    def _enqueue_tasks(self, plan: PlanOutput, trace_id: str = None):
        """将任务加入队列"""
        task_ids = []
        
        for task_def in plan.tasks:
            # 创建Task对象
            task = Task(
                action=task_def.action,
                params=task_def.params,
                description=task_def.description,
                max_retries=task_def.retry,
                timeout=task_def.timeout,
                depends_on=task_def.depends_on or [],
                trace_id=trace_id
            )
            
            # 使用指定的ID
            task.task_id = task_def.id
            
            # 加入队列
            task_id = self.task_queue.add_task(task)
            task_ids.append(task_id)
        
        self.logger.info(
            f"Enqueued {len(task_ids)} tasks",
            trace_id=trace_id,
            component="TaskPlanner",
            context={"task_ids": task_ids}
        )
        
        # 发布任务已创建事件
        self.event_bus.publish_simple(
            EventType.TASK_PLANNED.value,
            {
                "goal": plan.goal,
                "task_count": len(task_ids),
                "task_ids": task_ids,
                "estimated_time": plan.estimated_time
            },
            trace_id=trace_id
        )
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计"""
        return self.task_queue.get_stats()


class RuleBasedPlanner:
    """
    基于规则的规划器
    
    高频场景，无需LLM
    """
    
    RULES = {
        "health_check": {
            "pattern": "检查|health|status",
            "tasks": [
                {
                    "action": "run_command",
                    "params": {"command": "python3 /root/.openclaw/workspace/tools/health_check.py"},
                    "description": "运行健康检查",
                    "timeout": 60
                }
            ]
        },
        "git_commit": {
            "pattern": "提交|commit|git",
            "tasks": [
                {
                    "action": "run_command",
                    "params": {"command": "git add -A && git commit -m 'update'"},
                    "description": "提交Git更改",
                    "timeout": 30
                }
            ]
        },
        "backup": {
            "pattern": "备份|backup",
            "tasks": [
                {
                    "action": "run_command",
                    "params": {"command": "cp -r /root/.openclaw/workspace /root/.openclaw/backup/$(date +%Y%m%d_%H%M%S)"},
                    "description": "备份工作目录",
                    "timeout": 120
                }
            ]
        }
    }
    
    @classmethod
    def try_plan(cls, goal: str) -> Optional[PlanOutput]:
        """尝试规则匹配"""
        import re
        
        for rule_name, rule in cls.RULES.items():
            if re.search(rule["pattern"], goal, re.IGNORECASE):
                tasks = [
                    TaskDefinition(**task_def)
                    for task_def in rule["tasks"]
                ]
                
                return PlanOutput(
                    goal=goal,
                    tasks=tasks,
                    estimated_time=sum(t.timeout for t in tasks) // 60 + 1,
                    reasoning=f"Rule-based planning: {rule_name}"
                )
        
        return None


# 全局实例
_planner_instance: Optional[TaskPlanner] = None


def get_planner() -> TaskPlanner:
    """获取全局任务规划器"""
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = TaskPlanner()
    return _planner_instance


def set_planner(planner: TaskPlanner):
    """设置全局任务规划器"""
    global _planner_instance
    _planner_instance = planner