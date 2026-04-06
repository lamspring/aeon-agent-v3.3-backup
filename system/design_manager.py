#!/usr/bin/env python3
"""
Design Manager - 设计文档管理器

管理架构变更的设计文档：
  - 创建新设计
  - 更新设计状态
  - 审批设计
  - 列出所有设计
"""
import json
import re
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
DESIGNS_DIR = AGENT_DIR / "designs"
GOVERNANCE_FILE = AGENT_DIR / "system" / "architecture_governance.json"

def log_simple(msg):
    """简化日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = AGENT_DIR / "logs" / "execution_log.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] [DESIGN] {msg}\n")

class DesignManager:
    """设计文档管理器"""
    
    def __init__(self):
        DESIGNS_DIR.mkdir(parents=True, exist_ok=True)
        self.governance = self._load_governance()
    
    def _load_governance(self):
        """加载治理配置"""
        if GOVERNANCE_FILE.exists():
            with open(GOVERNANCE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"governance_enabled": False}
    
    def _save_governance(self):
        """保存治理配置"""
        with open(GOVERNANCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.governance, f, indent=2, ensure_ascii=False)
    
    def create_design(self, title: str, description: str) -> str:
        """
        创建新设计文档
        
        Args:
            title: 设计标题
            description: 简要描述
            
        Returns:
            设计文档路径
        """
        # 生成设计ID
        date_str = datetime.now().strftime("%Y%m%d")
        
        # 查找当天的设计编号
        existing = list(DESIGNS_DIR.glob(f"DESIGN_{date_str}_*.md"))
        max_num = 0
        for f in existing:
            match = re.search(rf"DESIGN_{date_str}_(\d+)", f.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        
        new_num = max_num + 1
        design_id = f"DESIGN_{date_str}_{new_num:03d}"
        
        # 读取模板
        template_file = DESIGNS_DIR / "TEMPLATE.md"
        if template_file.exists():
            with open(template_file, 'r', encoding='utf-8') as f:
                template = f.read()
        else:
            template = "# Design Document\n\n## 基本信息\n- **设计ID**: {design_id}\n"
        
        # 填充模板
        content = template.replace("DESIGN_YYYYMMDD_NNN", design_id)
        content = content.replace("[简要描述]", title)
        content = content.replace("YYYY-MM-DD", datetime.now().strftime("%Y-%m-%d"))
        content = content.replace("[你的名字]", "Agent")
        
        # 写入文件
        design_file = DESIGNS_DIR / f"{design_id}.md"
        with open(design_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 更新治理记录
        self.governance.setdefault("current_designs", []).append({
            "id": design_id,
            "title": title,
            "status": "PENDING",
            "created_at": datetime.now().isoformat()
        })
        self._save_governance()
        
        log_simple(f"Created design: {design_id} - {title}")
        
        return str(design_file)
    
    def update_status(self, design_id: str, new_status: str, comment: str = ""):
        """
        更新设计状态
        
        Args:
            design_id: 设计ID
            new_status: 新状态
            comment: 备注
        """
        # 验证状态转换
        valid_states = self.governance.get("workflow", {}).get("states", [])
        if new_status not in valid_states:
            print(f"❌ 无效状态: {new_status}")
            return False
        
        # 更新治理记录
        for design in self.governance.get("current_designs", []):
            if design["id"] == design_id:
                old_status = design["status"]
                design["status"] = new_status
                design["updated_at"] = datetime.now().isoformat()
                if comment:
                    design.setdefault("comments", []).append({
                        "timestamp": datetime.now().isoformat(),
                        "comment": comment
                    })
                
                self._save_governance()
                log_simple(f"Updated {design_id}: {old_status} → {new_status}")
                print(f"✅ {design_id}: {old_status} → {new_status}")
                return True
        
        print(f"❌ 设计不存在: {design_id}")
        return False
    
    def approve(self, design_id: str, approver: str = "朋朋"):
        """批准设计"""
        success = self.update_status(design_id, "APPROVED", f"Approved by {approver}")
        if success:
            print(f"🎉 {design_id} 已批准！现在可以开始实施。")
        return success
    
    def reject(self, design_id: str, reason: str = ""):
        """拒绝设计"""
        comment = f"Rejected. Reason: {reason}" if reason else "Rejected"
        success = self.update_status(design_id, "REJECTED", comment)
        if success:
            print(f"❌ {design_id} 被拒绝。{reason}")
        return success
    
    def list_designs(self, status: str = None):
        """
        列出设计文档
        
        Args:
            status: 筛选状态，None表示全部
        """
        designs = self.governance.get("current_designs", [])
        
        if status:
            designs = [d for d in designs if d["status"] == status]
        
        if not designs:
            print("没有找到设计文档")
            return
        
        print(f"\n📋 设计文档列表 ({len(designs)}个):")
        print("-" * 60)
        
        for d in designs:
            status_icon = {
                "PENDING": "⏳",
                "APPROVED": "✅",
                "REJECTED": "❌",
                "IMPLEMENTING": "🔨",
                "VERIFYING": "🧪",
                "COMPLETED": "🎉",
                "ROLLED_BACK": "↩️"
            }.get(d["status"], "❓")
            
            print(f"{status_icon} {d['id']}: {d['title']}")
            print(f"   状态: {d['status']} | 创建: {d.get('created_at', 'N/A')[:10]}")
            
            # 检查文件是否存在
            design_file = DESIGNS_DIR / f"{d['id']}.md"
            if design_file.exists():
                print(f"   文件: {design_file}")
        
        print()
    
    def get_pending_count(self) -> int:
        """获取待审批的设计数量"""
        designs = self.governance.get("current_designs", [])
        return len([d for d in designs if d["status"] == "PENDING"])
    
    def check_can_modify_code(self) -> bool:
        """
        检查是否可以修改代码
        
        Returns:
            True if governance is disabled or there are approved designs ready
        """
        if not self.governance.get("governance_enabled", False):
            return True
        
        # 检查是否有已批准的设计正在实施
        designs = self.governance.get("current_designs", [])
        implementing = [d for d in designs if d["status"] in ["APPROVED", "IMPLEMENTING"]]
        
        return len(implementing) > 0
    
    def get_status(self) -> dict:
        """获取治理状态"""
        designs = self.governance.get("current_designs", [])
        return {
            "governance_enabled": self.governance.get("governance_enabled", False),
            "total_designs": len(designs),
            "pending": len([d for d in designs if d["status"] == "PENDING"]),
            "approved": len([d for d in designs if d["status"] == "APPROVED"]),
            "implementing": len([d for d in designs if d["status"] == "IMPLEMENTING"]),
            "completed": len([d for d in designs if d["status"] == "COMPLETED"]),
            "can_modify_code": self.check_can_modify_code()
        }

if __name__ == "__main__":
    import sys
    
    manager = DesignManager()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 design_manager.py create \"标题\" \"描述\"")
        print("  python3 design_manager.py approve DESIGN_20260405_001")
        print("  python3 design_manager.py reject DESIGN_20260405_001 \"原因\"")
        print("  python3 design_manager.py list")
        print("  python3 design_manager.py status")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "create":
        if len(sys.argv) < 3:
            print("❌ 需要提供标题")
            sys.exit(1)
        title = sys.argv[2]
        desc = sys.argv[3] if len(sys.argv) > 3 else ""
        path = manager.create_design(title, desc)
        print(f"✅ 设计文档已创建: {path}")
    
    elif command == "approve":
        if len(sys.argv) < 3:
            print("❌ 需要提供设计ID")
            sys.exit(1)
        manager.approve(sys.argv[2])
    
    elif command == "reject":
        if len(sys.argv) < 3:
            print("❌ 需要提供设计ID")
            sys.exit(1)
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        manager.reject(sys.argv[2], reason)
    
    elif command == "list":
        manager.list_designs()
    
    elif command == "status":
        status = manager.get_status()
        print("\n📊 架构治理状态:")
        print(f"  治理启用: {status['governance_enabled']}")
        print(f"  总设计数: {status['total_designs']}")
        print(f"  待审批: {status['pending']}")
        print(f"  已批准: {status['approved']}")
        print(f"  实施中: {status['implementing']}")
        print(f"  已完成: {status['completed']}")
        print(f"  可修改代码: {status['can_modify_code']}")
    
    else:
        print(f"❌ 未知命令: {command}")
