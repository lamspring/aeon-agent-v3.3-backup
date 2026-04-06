#!/usr/bin/env python3
"""
Aeon CLI - 命令行管理工具

Usage:
    ./aeon-cli.py goals list              # 列出所有目标
    ./aeon-cli.py goals create "描述"     # 创建目标
    ./aeon-cli.py goals complete <id>     # 完成目标
    ./aeon-cli.py events status           # 查看事件队列
    ./aeon-cli.py status                  # 系统整体状态
"""

import sys
import argparse
import json
from datetime import datetime
from typing import Optional

sys.path.insert(0, '/root/.openclaw/workspace/agent')

from goals import GoalManager, GoalPriority
from bus.event_bus_v2 import get_event_bus
from cognition.cognition_loop import get_cognition


def format_time(ts: Optional[float]) -> str:
    """格式化时间戳"""
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def format_duration(seconds: Optional[float]) -> str:
    """格式化持续时间"""
    if not seconds:
        return "-"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds/60)}m"
    return f"{seconds/3600:.1f}h"


class GoalsCommand:
    """Goal 管理命令"""
    
    def __init__(self):
        self.gm = GoalManager()
    
    def list(self, status: Optional[str] = None, limit: int = 20):
        """列出目标"""
        goals = self.gm.list_goals()
        
        if status:
            goals = [g for g in goals if g.status == status]
        
        goals = goals[:limit]
        
        if not goals:
            print("No goals found.")
            return
        
        print(f"\n{'ID':<10} {'Status':<10} {'P':<3} {'Description':<40} {'Created'}")
        print("-" * 80)
        
        for g in goals:
            desc = g.description[:38] + ".." if len(g.description) > 40 else g.description
            print(f"{g.goal_id[:8]:<10} {g.status:<10} {g.priority:<3} {desc:<40} {format_time(g.created_at)}")
        
        print(f"\nTotal: {len(goals)} goals")
    
    def create(self, description: str, priority: str = "normal", keywords: str = ""):
        """创建目标"""
        priority_map = {
            "critical": GoalPriority.CRITICAL,
            "high": GoalPriority.HIGH,
            "normal": GoalPriority.NORMAL,
            "low": GoalPriority.LOW,
        }
        
        prio = priority_map.get(priority.lower(), GoalPriority.NORMAL)
        
        context = {}
        if keywords:
            context["keywords"] = [k.strip() for k in keywords.split(",")]
        
        goal = self.gm.create_goal(
            description=description,
            priority=prio,
            context=context
        )
        
        print(f"✓ Goal created: {goal.goal_id}")
        print(f"  Description: {description}")
        print(f"  Priority: {priority}")
        if keywords:
            print(f"  Keywords: {keywords}")
    
    def complete(self, goal_id: str):
        """完成目标"""
        # 尝试匹配前缀
        goal = self.gm.get_goal(goal_id)
        
        if not goal and len(goal_id) < 8:
            # 尝试搜索前缀匹配
            all_goals = self.gm.list_goals()
            matches = [g for g in all_goals if g.goal_id.startswith(goal_id)]
            if len(matches) == 1:
                goal = matches[0]
            elif len(matches) > 1:
                print(f"Ambiguous ID: {len(matches)} matches")
                return
        
        if not goal:
            print(f"Goal not found: {goal_id}")
            return
        
        if self.gm.complete_goal(goal.goal_id):
            print(f"✓ Goal completed: {goal.goal_id[:8]}...")
        else:
            print(f"✗ Failed to complete goal (status: {goal.status})")
    
    def show(self, goal_id: str):
        """显示目标详情"""
        goal = self.gm.get_goal(goal_id)
        
        if not goal and len(goal_id) < 8:
            all_goals = self.gm.list_goals()
            matches = [g for g in all_goals if g.goal_id.startswith(goal_id)]
            if len(matches) == 1:
                goal = matches[0]
        
        if not goal:
            print(f"Goal not found: {goal_id}")
            return
        
        print(f"\n{'='*50}")
        print(f"Goal: {goal.goal_id}")
        print(f"{'='*50}")
        print(f"Description: {goal.description}")
        print(f"Status: {goal.status}")
        print(f"Priority: {goal.priority}")
        print(f"Created: {format_time(goal.created_at)}")
        print(f"Activated: {format_time(goal.activated_at)}")
        print(f"Completed: {format_time(goal.completed_at)}")
        
        if goal.get_duration():
            print(f"Duration: {format_duration(goal.get_duration())}")
        
        print(f"\nKeywords: {', '.join(goal.get_keywords()) or 'None'}")
        print(f"Tasks: {len(goal.related_task_ids)}")
        
        if goal.failure_reason:
            print(f"\nFailure Reason: {goal.failure_reason}")
        
        if goal.result:
            print(f"\nResult:")
            print(json.dumps(goal.result, indent=2, ensure_ascii=False))
        
        print(f"{'='*50}")
    
    def activate_next(self):
        """激活下一个待处理目标"""
        goal = self.gm.activate_next_pending()
        if goal:
            print(f"✓ Activated: {goal.goal_id[:8]}... '{goal.description[:40]}'")
        else:
            print("No pending goals to activate.")
    
    def stats(self):
        """显示统计"""
        stats = self.gm.get_statistics()
        
        print("\n=== Goal Statistics ===")
        for status, count in sorted(stats.items()):
            print(f"  {status:<12}: {count}")
        
        active = self.gm.get_active_goal()
        if active:
            print(f"\nActive: {active.description[:50]}")
        else:
            print("\nActive: None")


class EventsCommand:
    """Event 管理命令"""
    
    def __init__(self):
        self.bus = get_event_bus()
    
    def status(self):
        """显示事件队列状态"""
        queue_size = self.bus.get_queue_size()
        
        print(f"\n=== Event Bus Status ===")
        print(f"Queue Size: {queue_size}")
        print(f"Worker ID: {self.bus.worker_id}")
        
        # 尝试获取死信
        try:
            dead = self.bus.get_dead_letters(limit=10)
            print(f"Dead Letters: {len(dead)}")
            if dead:
                print("\nRecent dead letters:")
                for e in dead[:5]:
                    print(f"  - {e.event_id[:8]}... {e.type} (retry: {e.retry_count})")
        except:
            pass
    
    def list_pending(self, limit: int = 10):
        """列出待处理事件"""
        events = self.bus.get_pending_events(limit=limit)
        
        if not events:
            print("No pending events.")
            return
        
        print(f"\n{'Type':<30} {'Status':<10} {'Retry':<5} {'Time'}")
        print("-" * 70)
        
        for e in events:
            print(f"{e.get('type','unknown'):<30} {e.get('status','?'):<10} {e.get('retry_count',0):<5} {format_time(e.get('timestamp'))}")
        
        print(f"\nTotal: {len(events)} events")


class StatusCommand:
    """系统状态命令"""
    
    def __init__(self):
        self.gm = GoalManager()
        self.bus = get_event_bus()
        self.cognition = get_cognition()
    
    def show(self):
        """显示整体状态"""
        print(f"\n{'='*60}")
        print("Aeon Agent v3.1 - System Status")
        print(f"{'='*60}")
        
        # Goal 状态
        goal_stats = self.gm.get_statistics()
        active_goal = self.gm.get_active_goal()
        
        print(f"\n📌 Goals:")
        for status, count in sorted(goal_stats.items()):
            print(f"   {status:<12}: {count}")
        
        if active_goal:
            print(f"\n   Active: {active_goal.description[:45]}")
        
        # Event 状态
        queue_size = self.bus.get_queue_size()
        print(f"\n📨 Events:")
        print(f"   Queue Size: {queue_size}")
        
        # Cognition 状态
        try:
            cog_status = self.cognition.get_status()
            print(f"\n🧠 Cognition:")
            print(f"   State: {cog_status.get('state')}")
            print(f"   Tick Count: {cog_status.get('tick_count')}")
            print(f"   Last Activity: {cog_status.get('last_activity', 'N/A')[:16]}")
        except:
            pass
        
        print(f"\n{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Aeon Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s goals list
  %(prog)s goals create "修复 bug" --priority high --keywords "bug,critical"
  %(prog)s goals complete abc123
  %(prog)s events status
  %(prog)s status
  %(prog)s dashboard    # Live monitoring
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Goals 子命令
    goals_parser = subparsers.add_parser('goals', help='Goal management')
    goals_sub = goals_parser.add_subparsers(dest='goals_cmd')
    
    # goals list
    list_cmd = goals_sub.add_parser('list', help='List goals')
    list_cmd.add_argument('--status', choices=['pending', 'active', 'completed', 'failed'])
    list_cmd.add_argument('--limit', type=int, default=20)
    
    # goals create
    create_cmd = goals_sub.add_parser('create', help='Create a goal')
    create_cmd.add_argument('description', help='Goal description')
    create_cmd.add_argument('--priority', choices=['critical', 'high', 'normal', 'low'], default='normal')
    create_cmd.add_argument('--keywords', help='Comma-separated keywords')
    
    # goals complete
    complete_cmd = goals_sub.add_parser('complete', help='Complete a goal')
    complete_cmd.add_argument('goal_id', help='Goal ID (or prefix)')
    
    # goals show
    show_cmd = goals_sub.add_parser('show', help='Show goal details')
    show_cmd.add_argument('goal_id', help='Goal ID (or prefix)')
    
    # goals activate
    activate_cmd = goals_sub.add_parser('activate', help='Activate next pending goal')
    
    # goals stats
    stats_cmd = goals_sub.add_parser('stats', help='Show goal statistics')
    
    # Events 子命令
    events_parser = subparsers.add_parser('events', help='Event management')
    events_sub = events_parser.add_subparsers(dest='events_cmd')
    
    # events status
    events_status_cmd = events_sub.add_parser('status', help='Show event queue status')
    
    # events list
    events_list_cmd = events_sub.add_parser('list', help='List pending events')
    events_list_cmd.add_argument('--limit', type=int, default=10)
    
    # Config 子命令
    config_parser = subparsers.add_parser('config', help='Configuration')
    config_sub = config_parser.add_subparsers(dest='config_cmd')
    
    # config show
    config_show_cmd = config_sub.add_parser('show', help='Show current config')
    
    # config set
    config_set_cmd = config_sub.add_parser('set', help='Set config value')
    config_set_cmd.add_argument('key', help='Config key (e.g. health_server.port)')
    config_set_cmd.add_argument('value', help='Config value')
    
    # Status 命令
    status_parser = subparsers.add_parser('status', help='Show system status')
    
    # Dashboard 命令
    dashboard_parser = subparsers.add_parser('dashboard', help='Live dashboard mode')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Dashboard 模式
    if args.command == 'dashboard':
        import time
        import os
        
        gm = GoalManager()
        bus = get_event_bus()
        
        try:
            while True:
                os.system('clear')
                
                print("=" * 60)
                print("Aeon Agent v3.1 - Live Dashboard (Ctrl+C to exit)")
                print("=" * 60)
                
                # Goals
                stats = gm.get_statistics()
                active = gm.get_active_goal()
                
                print(f"\n📌 Goals: {dict(stats)}")
                if active:
                    print(f"   Active: {active.description[:50]}")
                    print(f"   Tasks: {len(active.related_task_ids)}")
                
                # Events
                queue = bus.get_queue_size()
                print(f"\n📨 Events: Queue={queue}")
                
                # 时间
                print(f"\n⏱  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\nExiting...")
        return
    
    # 执行命令
    if args.command == 'goals':
        cmd = GoalsCommand()
        
        if args.goals_cmd == 'list':
            cmd.list(status=args.status, limit=args.limit)
        elif args.goals_cmd == 'create':
            cmd.create(args.description, args.priority, args.keywords or "")
        elif args.goals_cmd == 'complete':
            cmd.complete(args.goal_id)
        elif args.goals_cmd == 'show':
            cmd.show(args.goal_id)
        elif args.goals_cmd == 'activate':
            cmd.activate_next()
        elif args.goals_cmd == 'stats':
            cmd.stats()
        else:
            goals_parser.print_help()
    
    elif args.command == 'events':
        cmd = EventsCommand()
        
        if args.events_cmd == 'status':
            cmd.status()
        elif args.events_cmd == 'list':
            cmd.list_pending(limit=args.limit)
        else:
            events_parser.print_help()
    
    elif args.command == 'status':
        cmd = StatusCommand()
        cmd.show()
    
    elif args.command == 'config':
        from config import get_config
        config = get_config()
        
        if args.config_cmd == 'show':
            import json
            print(json.dumps({
                "health_server": {
                    "enabled": config.health_server.enabled,
                    "host": config.health_server.host,
                    "port": config.health_server.port,
                },
                "cognition": {
                    "tick_interval": config.cognition.tick_interval,
                    "idle_timeout": config.cognition.idle_timeout,
                },
                "attention": {
                    "max_events_per_tick": config.attention.max_events_per_tick,
                    "decay_factor": config.attention.decay_factor,
                },
            }, indent=2))
        elif args.config_cmd == 'set':
            config.set(args.key, args.value)
            config.save()
            print(f"✓ Config updated: {args.key} = {args.value}")
        else:
            config_parser.print_help()


if __name__ == '__main__':
    main()
