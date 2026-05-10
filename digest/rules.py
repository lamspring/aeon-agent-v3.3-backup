import re
from typing import List, Dict, Tuple
from datetime import datetime
from digest.models import MessageDigest, DailyDigest

# 主题关键词映射（精简版，避免Python字符串长度限制）
TOPIC_KEYWORDS = {
    "技术": [
        "代码", "bug", "报错", "修复", "系统", "api", "python", "数据库", "架构", "设计",
        "mimo", "子代理", "程序", "函数", "接口", "部署", "服务器", "git", "测试", "调试",
        "优化", "性能", "模型", "算法", "前端", "后端", "框架", "docker", "k8s", "ci/cd",
        "github", "gitlab", "npm", "pip", "sdk", "模块", "微服务", "http", "https", "认证",
        "授权", "安全", "漏洞", "sql", "redis", "mongodb", "mysql", "kafka", "消息队列",
        "定时任务", "调度", "日志", "监控", "linux", "bash", "shell", "脚本", "llm", "大模型",
        "agent", "智能体", "rag", "向量", "embedding", "prompt", "微调", "推理", "pytorch",
        "transformers", "llama", "qwen", "deepseek", "kimi", "gpt", "claude", "训练", "数据",
        "分析", "etl", "机器学习", "深度学习", "神经网络", "transformer", "nlp", "计算机视觉",
        "强化学习", "搜索", "排序", "ab测试", "可视化", "dashboard", "统计", "因果推断",
        "聚类", "分类", "回归", "预测", "联邦学习", "隐私计算", "密码学", "加密", "签名",
        "哈希", "tls", "waf", "防火墙", "渗透测试", "ctf", "缓冲区溢出", "rop", "对抗样本",
        "可解释性", "压缩", "编码", "索引", "b树", "b+树", "跳表", "红黑树", "动态规划",
        "递归", "分治", "贪心", "回溯", "蒙特卡洛", "元学习", "vae", "gan", "diffusion",
        "cnn", "rnn", "lstm", "bert", "stable diffusion", "多模态", "vlm", "ocr", "语音识别",
        "语音合成", "gpu", "cuda", "nvidia", "并行", "并发", "异步", "协程", "线程", "进程",
        "内存", "缓存", "锁", "死锁", "分布式", "一致性", "事务", "acid", "raft", "区块链",
        "零知识证明", "wasm", "rust", "go", "c++", "java", "kotlin", "swift", "rust", "flutter",
        "react native", "electron", "unity", "unreal", "godot", "ecs", "游戏引擎", "物理引擎",
        "渲染", "光线追踪", "粒子", "流体", "动画", "导航", "寻路", "a*", "行为树", "状态机",
        "对话系统", "chatbot", "语音助手", "虚拟人", "数字人", "元宇宙", "vr", "ar", "mr",
        "手势识别", "姿态估计", "人脸", "目标检测", "yolo", "分割", "深度估计", "光流",
        "slam", "点云", "nerf", "gaussian splatting", "3dgs", "自动驾驶", "adas", "智能座舱",
        "车联网", "v2x", "域控制器", "soc", "mcu", "ecu", "autosar", "ros", "中间件",
        "can", "以太网", "功能安全", "网络安全", "诊断", "uds", "hil", "快速原型",
        "自动代码生成", "需求工程", "alm", "plm", "devops", "sre", "混沌工程", "容灾",
        "备份", "恢复", "sla", "可用性", "可靠性", "弹性", "韧性", "容错", "降级", "熔断",
        "限流", "隔离", "超时", "重试", "幂等", "负载均衡", "nginx", "haproxy", "envoy",
        "istio", "service mesh", "cdn", "边缘计算", "5g", "6g", "基站", "物联网", "iot",
        "智能家居", "智慧城市", "智慧医疗", "智能制造", "数字孪生", "scada", "mes", "erp",
        "crm", "wms", "计费", "支付", "清算", "风控", "反欺诈", "规则引擎", "决策树",
        "随机森林", "xgboost", "lightgbm", "特征工程", "数据清洗", "数据标注", "数据增强",
        "隐私计算", "联邦学习", "差分隐私", "可信执行环境", "tee", "wasm", "webassembly",
        "gpu", "cuda", "并行计算", "分布式计算", "边缘计算", "雾计算", "云计算", "云原生",
        "serverless", "faas", "paas", "iaas", "saas", "draas", "bpaas", "maas", "aiaas"
    ],
    "创作": [
        "小说", "写作", "故事", "编辑", "章节", "审稿", "恶灵游戏", "剧本", "大纲",
        "人设", "世界观", "情节", "伏笔", "悬念", "反转", "高潮", "结局", "开头",
        "文笔", "描写", "对话", "叙事", "视角", "第一人称", "第三人称", "主角",
        "配角", "反派", "boss", "副本", "系统", "金手指", "爽文", "虐文", "甜文",
        "悬疑", "推理", "恐怖", "灵异", "玄幻", "仙侠", "武侠", "科幻", "末世",
        "无限流", "快穿", "重生", "穿越", "系统流", "种田", "基建", "经营", "权谋",
        "宫斗", "宅斗", "商战", "职场", "校园", "青春", "恋爱", "耽美", "百合",
        "言情", "纯爱", "无cp", "群像", "多主角", "单元剧", "单元", "短篇", "中篇",
        "长篇", "连载", "完结", "太监", "断更", "日更", "双更", "爆更", "存稿",
        "大纲", "细纲", "章纲", "卡文", "灵感", "脑洞", "设定", "设定集", "番外",
        "前传", "后传", "外传", "同人", "二创", "衍生", "改编", "影视化", "动画化",
        "漫画", "广播剧", "有声书", "出版", "签约", "上架", "推荐", "榜单", "月票",
        "订阅", "收藏", "点击", "评论", "书评", "段评", "本章说", "书单", "推书",
        # 🦞 虾虾新增：创作过程词
        "写了", "写了三千字", "写了很久", "写了半天", "写了一整天",
        "累死了", "累瘫", "累垮", "累坏", "累倒",
        "卡文", "写不动", "没灵感", "写不出来", "瓶颈",
        "审稿", "校稿", "改稿", "润色", "修改", "修订",
        "大纲", "细纲", "章纲", "设定", "世界观", "人设"
    ],
    "情感": [
        "想你", "爱你", "mua", "宝贝", "晚安", "亲", "抱", "贴贴", "摸摸", "蹭蹭",
        "撒娇", "委屈", "难过", "开心", "高兴", "快乐", "幸福", "满足", "安心",
        "担心", "牵挂", "思念", "惦记", "在乎", "重视", "珍惜", "珍惜", "珍贵",
        "特别", "唯一", "专属", "独占", "私有", "亲密", "暧昧", "温柔", "体贴",
        "细心", "耐心", "包容", "理解", "支持", "陪伴", "守护", "照顾", "关心",
        "牵挂", "惦念", "想念", "思念", "怀念", "回忆", "纪念", "礼物", "惊喜",
        "浪漫", "仪式感", "表白", "告白", "求婚", "订婚", "结婚", "婚礼", "蜜月",
        "纪念日", "生日", "节日", "情人节", "七夕", "520", "1314", "一生一世",
        "永远", "长久", "永恒", "不朽", "不灭", "不老", "不散", "不离", "不弃",
        "不分离", "在一起", "一辈子", "一生一世", "生生世世", "来生来世", "三生三世"
    ],
    "系统": [
        "aeon", "openclaw", "配置", "部署", "日志", "cron", "定时任务", "系统服务",
        "systemd", "开机启动", "自启动", "守护进程", "daemon", "进程管理", "进程守护",
        "监控", "告警", "报警", "通知", "推送", "心跳", "health check", "健康检查",
        "状态", "状态码", "http", "https", "端口", "防火墙", "iptables", "ufw",
        "端口转发", "反向代理", "正向代理", "负载均衡", "nginx", "haproxy", "traefik",
        "envoy", "dns", "域名", "解析", "cdn", "缓存", "ttl", "证书", "ssl", "tls",
        "https", "acme", "letsencrypt", "证书续期", "证书过期", "pem", "crt", "key",
        "私钥", "公钥", "密钥", "加密", "解密", "base64", "hash", "md5", "sha",
        "sha256", "签名", "验签", "token", "jwt", "oauth", "openid", "sso", "认证",
        "鉴权", "授权", "权限", "rbac", "acl", "策略", "角色", "用户", "组",
        "租户", "命名空间", "namespace", "资源", "配额", "限制", "限速", "限流",
        "配额管理", "资源管理", "调度", "编排", "编排器", "调度器", "集群", "节点",
        "node", "pod", "容器", "container", "镜像", "image", "仓库", "registry",
        "harbor", "docker hub", "ghcr", "构建", "打包", "发布", "部署", "回滚",
        "灰度", "蓝绿", "金丝雀", "canary", "ab测试", "分流", "流量", "流量管理",
        "链路追踪", "trace", "span", "jaeger", "zipkin", "skywalking", "日志",
        "log", "日志收集", "日志聚合", "elk", "efk", "loki", "fluentd", "fluent bit",
        "filebeat", "logstash", "grafana", "prometheus", "metrics", "指标", "指标收集",
        "监控", "observability", "可观测性", "trace", "metric", "log", "事件",
        "event", "审计", "audit", "审计日志", "操作日志", "变更记录", "历史记录",
        "备份", "快照", "恢复", "还原", "容灾", "灾备", "异地多活", "同城双活",
        "冷备", "热备", "温备", "rto", "rpo", "sla", "可用性", "可靠性", "稳定性",
        "容灾演练", "故障演练", "混沌工程", "chaos engineering", "故障注入",
        "故障转移", "failover", "主备切换", "脑裂", "split brain", "选举", "投票",
        "共识", "一致性", "最终一致性", "强一致性", "线性一致性", "顺序一致性",
        "因果一致性", "会话一致性", "单调一致性", "读写一致性", "写后读一致性",
        "单调读", "单调写", "读己之所写", "管道一致性", "时间戳", "向量时钟",
        "happens before", "并发控制", "锁", "乐观锁", "悲观锁", "mvcc", "版本控制",
        "事务", "acid", "base", " saga", "tcc", "2pc", "3pc", "xa", "本地消息表",
        "消息队列", "kafka", "rabbitmq", "rocketmq", "pulsar", "nsq", "nats",
        "mqtt", "amqp", "pub/sub", "发布订阅", "消息", "事件", "事件驱动",
        "event driven", "eda", "cqrs", "事件溯源", "event sourcing", "流处理",
        "stream processing", "实时", "实时计算", "批处理", "离线", "近实时",
        "lambda", "kappa", "数据流", "dataflow", "数据管道", "etl", "elt", "数据集成",
        "数据同步", "数据迁移", "数据转换", "数据清洗", "数据质量", "数据治理",
        "元数据", "数据目录", "数据资产", "数据血缘", "数据影响分析", "数据发现",
        "数据安全", "数据加密", "数据脱敏", "数据掩码", "数据分类", "数据分级",
        "数据生命周期", "数据保留", "数据归档", "数据删除", "数据销毁", "合规",
        "gdpr", "ccpa", "等保", "网络安全法", "数据安全法", "个人信息保护法",
        "隐私", "隐私保护", "隐私增强", "差分隐私", "联邦学习", "安全多方计算",
        "同态加密", "可信执行环境", "tee", "sgx", "硬件安全模块", "hsm", "密钥管理",
        "kms", "证书管理", "pki", "ca", "根证书", "中间证书", "终端证书", "吊销",
        "crl", "ocsp", "证书透明", "ct", "dnssec", "dane", "mta-sts", "dmarc",
        "spf", "dkim", "邮件安全", "反垃圾", "反钓鱼", "反欺诈", "内容安全",
        "内容审核", "敏感词", "过滤", "屏蔽", "黑名单", "白名单", "灰名单",
        "策略", "规则", "规则引擎", "drools", "easy rules", "风控", "风控引擎",
        "反作弊", "防盗刷", "防羊毛", "防爬虫", "防攻击", "ddos", "cc攻击",
        "waf", "rasp", "hids", "nids", "ips", "ids", "siem", "soc", "威胁情报",
        "ioc", "失陷指标", "apt", "高级威胁", "持久化", "后门", "webshell",
        "木马", "病毒", "蠕虫", "勒索", "挖矿", "僵尸网络", "botnet", "c2",
        "命令控制", "流量分析", "行为分析", "ueba", "异常检测", "欺诈检测",
        "洗钱", "aml", "kyc", "尽职调查", "合规检查", "审计", "内审", "外审",
        "财务审计", "安全审计", "it审计", "系统审计", "代码审计", "渗透测试",
        "漏洞扫描", "基线检查", "配置核查", "资产发现", "资产管理", "it资产管理",
        "cmdb", "配置管理", "变更管理", "事件管理", "问题管理", "itil", "itsm",
        "servicedesk", "服务台", "工单", "ticket", "工单系统", "jira", "redmine",
        "禅道", "teambition", "tower", "ones", "tapd", "飞书", "lark", "钉钉",
        "企业微信", "wecom", "slack", "teams", "discord", "notion", "confluence",
        "wiki", "知识库", "文档", "协作", "协同", "办公", "oa", "erp", "crm",
        "scm", "plm", "mes", "wms", "tms", "oms", "billing", "计费", "支付",
        "清算", "结算", "对账", "发票", "税务", "财务", "会计", "出纳", "预算",
        "成本", "费用", "报销", "审批", "流程", "工作流", "bpm", "workflow",
        "activiti", "camunda", "flowable", "jbpm", "规则流", "决策流", "编排",
        "编排器", "orchestrator", "scheduler", "调度器", "定时任务", "job",
        "task", "cron", "quartz", "xxl-job", "elasticjob", "powerjob", "saturn",
        "tbschedule", "opencron", "crontab", "计划任务", "周期任务", "延迟任务",
        "定时触发", "事件触发", "消息触发", "api触发", "webhook", "回调",
        "通知", "提醒", "告警", "报警", "预警", "提示", "推送", "push", "短信",
        "邮件", "站内信", "app推送", "微信推送", "飞书推送", "钉钉推送",
        "slack通知", "webhook通知", "事件通知", "变更通知", "状态通知",
        "进度通知", "结果通知", "完成通知", "失败通知", "异常通知", "超时通知",
        "重试通知", "降级通知", "熔断通知", "限流通知", "降级通知", "扩容通知",
        "缩容通知", "上线通知", "下线通知", "发布通知", "回滚通知", "切换通知"
    ]
}

# 情绪关键词映射
EMOTION_KEYWORDS = {
    "positive": [
        "好", "棒", "赞", "开心", "高兴", "喜欢", "爱", "优秀", "厉害", "完美",
        "不错", "可以", "行", "ok", "好的", "没问题", "没问题", "太好了", "真棒",
        "太棒了", "非常好", "很满意", "很高兴", "很愉快", "很顺利", "很成功",
        "完成", "搞定", "解决", "修复", "恢复", "正常", "稳定", "健康", "良好",
        "优秀", "出色", "精彩", "漂亮", "美观", "好看", "好听", "好吃", "好喝",
        "好玩", "有趣", "有意思", "有意义", "有价值", "有帮助", "有用", "有效",
        "高效", "快捷", "方便", "便捷", "舒适", "舒服", "轻松", "愉快", "快乐",
        "幸福", "满足", "满意", "安心", "放心", "信任", "可靠", "可信", "诚实",
        "真诚", "真心", "真意", "热情", "热心", "积极", "主动", "进取", "努力",
        "奋斗", "拼搏", "坚持", "毅力", "决心", "信心", "勇气", "勇敢", "大胆",
        "果断", "坚定", "坚强", "韧性", "弹性", "适应", "灵活", "机智", "聪明",
        "智慧", "明智", "理性", "合理", "合规", "合法", "正当", "正义", "公平",
        "公正", "公开", "透明", "清晰", "清楚", "明白", "明确", "确定", "肯定",
        "确认", "保证", "确保", "保障", "维护", "保护", "守护", "关爱", "关怀",
        "关心", "体贴", "细心", "周到", "全面", "完整", "完善", "完美", "圆满",
        "成功", "胜利", "获胜", "夺冠", "第一名", "冠军", "金牌", "优秀", "杰出",
        "卓越", "非凡", "出色", "精彩", "精湛", "高超", "一流", "顶级", "顶尖",
        "领先", "先锋", "先驱", "开创", "创新", "创造", "创作", "发明", "发现",
        "探索", "探险", "冒险", "挑战", "突破", "超越", "飞跃", "腾飞", "崛起",
        "振兴", "复兴", "繁荣", "昌盛", "兴旺", "发达", "富强", "强大", "壮大",
        "成长", "进步", "提高", "提升", "升级", "优化", "改进", "改善", "改良",
        "改革", "变革", "革命", "革新", "更新", "换代", "迭代", "演进", "进化",
        "演化", "发展", "前进", "推进", "推动", "促进", "带动", "引领", "引导",
        "指导", "教导", "教育", "培训", "学习", "成长", "进步", "提升", "升华",
        # 🦞 虾虾新增：创作完成/亲密/心情
        "写完了", "完成了", "搞定了", "通过了", "审完了", "发表了",
        "晚安", "mua", "亲亲", "抱抱", "贴贴", "摸摸", "蹭蹭",
        "心情不错", "心情好", "开心", "高兴", "棒",
        "真棒", "太棒了", "完美", "优秀", "出色", "精彩"
    ],
    "negative": [
        "烦", "累", "bug", "报错", "出错", "失败", "不行", "不对", "错误",
        "异常", "问题", "故障", "中断", "停止", "崩溃", "死机", "卡住", "卡死",
        "无响应", "超时", "超时", "拒绝", "禁止", "阻止", "拦截", "阻断",
        "失败", "不成功", "未成功", "没成功", "失败", "错误", "失误", "过失",
        "疏忽", "大意", "粗心", "遗漏", "缺失", "缺少", "不足", "不够", "不够",
        "缺乏", "匮乏", "短缺", "紧张", "困难", "艰难", "艰巨", "辛苦", "劳累",
        "疲惫", "疲劳", "倦怠", "厌倦", "厌烦", "厌恶", "反感", "抵触", "排斥",
        "拒绝", "抵制", "反对", "抗议", "抗争", "反抗", "叛逆", "逆反", "违规",
        "违章", "违法", "犯罪", "罪恶", "邪恶", "恶毒", "狠毒", "阴险", "狡诈",
        "欺骗", "诈骗", "欺诈", "虚假", "伪造", "假冒", "冒充", "冒牌", "盗版",
        "侵权", "抄袭", "剽窃", "偷窃", "盗窃", "抢劫", "掠夺", "抢夺", "侵占",
        "贪污", "腐败", "堕落", "沉沦", "沦陷", "覆灭", "毁灭", "破坏", "毁坏",
        "损坏", "损害", "伤害", "危害", "危险", "风险", "隐患", "威胁", "恐吓",
        "吓唬", "威胁", "勒索", "敲诈", "碰瓷", "讹诈", "欺诈", "骗局", "陷阱",
        "圈套", "圈套", "圈套", "圈套", "圈套", "圈套", "圈套", "圈套",
        # 🦞 虾虾新增：创作痛苦
        "累死了", "累瘫", "累垮", "累坏", "累倒",
        "卡文", "写不动", "没灵感", "写不出来", "瓶颈"
    ]
}

# 显式待办触发词
TODO_TRIGGERS = [
    "帮我", "查一下", "看一下", "修一下", "改一下", "确认", "测试", "验证",
    "检查一下", "核实一下", "确认一下", "调查一下", "研究一下", "分析一下",
    "处理一下", "解决一下", "优化一下", "调整一下", "修改一下", "更新一下",
    "同步一下", "备份一下", "恢复一下", "重启一下", "重试", "重跑", "重做",
    "重新", "再来", "再试", "再查", "再看", "再修", "再改", "再确认", "再测试",
    "再验证", "执行", "运行", "启动", "停止", "关闭", "开启", "禁用", "启用",
    "配置", "设置", "调整", "修改", "更改", "变更", "更新", "升级", "降级",
    "回滚", "切换", "迁移", "转换", "替换", "删除", "清理", "清除", "重置",
    "初始化", "格式化", "重装", "部署", "发布", "上线", "下线", "灰度", "全量",
    "分批次", "逐步", "滚动", "增量", "全量", "差分", "对比", "比较", "核对",
    "校验", "检验", "审查", "审核", "审批", "批准", "同意", "拒绝", "驳回",
    "退回", "打回", "重做", "返工", "修补", "补救", "挽救", "挽回", "弥补",
    "补偿", "赔偿", "追责", "问责", "处分", "处罚", "惩罚", "制裁", "打击",
    "治理", "整改", "整顿", "清理", "肃清", "清除", "铲除", "根除", "消灭",
    "杜绝", "防止", "防范", "预防", "预警", "预报", "预测", "预估", "估算",
    "测算", "计算", "核算", "统计", "汇总", "总结", "归纳", "概括", "提炼",
    "萃取", "提取", "抽取", "挖掘", "发掘", "发现", "察觉", "觉察", "意识",
    "认识", "认知", "理解", "了解", "掌握", "熟悉", "熟练", "精通", "擅长",
    "专长", "专业", "专家", "能手", "高手", "大师", "宗师", "泰斗", "权威",
    "标杆", "典范", "楷模", "榜样", "模范", "标兵", "先进", "优秀", "杰出",
    "卓越", "非凡", "出色", "精彩", "精湛", "高超", "一流", "顶级", "顶尖",
    "领先", "先锋", "先驱", "开创", "创新", "创造", "创作", "发明", "发现",
    # 🦞 虾虾新增：隐含求助
    "怎么修", "怎么办", "怎么处理", "怎么解决", "怎么弄", "怎么搞",
    "不会修", "不会弄", "不会搞", "搞不定", "修不好", "弄不好",
    "求助", "求救", "帮帮忙", "帮个忙", "搭把手", "指点一下"
]

# 纯陈述排除词（出现这些词时不算待办）
TODO_EXCLUDE = [
    "崩了", "挂了", "坏了", "出问题了", "出bug了", "报错了",
    "不行了", "不行了", "不行了", "不行了"
]


def analyze_topic(content: str) -> str:
    """规则分析主题，返回最匹配的主题或'日常'"""
    content_lower = content.lower()
    scores = {}
    
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in content_lower:
                score += 1
        if score > 0:
            scores[topic] = score
    
    if not scores:
        return "日常"
    
    return max(scores, key=scores.get)


def analyze_emotion(content: str) -> str:
    """规则分析情绪，返回 positive/neutral/negative"""
    # 保守策略：都不确定时返回 neutral
    content_lower = content.lower()
    
    pos_score = 0
    neg_score = 0
    
    for kw in EMOTION_KEYWORDS["positive"]:
        if kw in content_lower:
            pos_score += 1
    
    for kw in EMOTION_KEYWORDS["negative"]:
        if kw in content_lower:
            neg_score += 1
    
    if pos_score > neg_score:
        return "positive"
    elif neg_score > pos_score:
        return "negative"
    else:
        return "neutral"


def is_explicit_todo(content: str) -> bool:
    """判断是否显式待办"""
    content_lower = content.lower()
    
    # 先检查排除词（纯陈述，不算待办）
    for exclude in TODO_EXCLUDE:
        if exclude in content_lower:
            # 但如果同时有明确的求助词，还是算待办
            has_explicit_help = any(t in content_lower for t in ["帮我", "查一下", "看一下", "修一下", "改一下", "怎么修", "怎么办", "求助", "帮帮忙"])
            if not has_explicit_help:
                return False
    
    # 再检查触发词
    return any(trigger in content_lower for trigger in TODO_TRIGGERS)


def analyze_message(message: Dict) -> MessageDigest:
    """分析单条消息，返回 MessageDigest"""
    content = message.get("message", "")
    ts_str = message.get("timestamp", "")
    
    # 解析时间
    try:
        if isinstance(ts_str, str):
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        else:
            ts = datetime.fromtimestamp(ts_str)
        ts = ts.replace(tzinfo=None)
    except:
        ts = datetime.now()
    
    # 截断内容预览
    preview = content[:100] if len(content) > 100 else content
    
    return MessageDigest(
        message_id=message.get("message_id", ""),
        timestamp=ts,
        channel=message.get("channel", "unknown"),
        user_id=message.get("user_id", "unknown"),
        content_preview=preview,
        topic=analyze_topic(content),
        emotion=analyze_emotion(content),
        is_explicit_todo=is_explicit_todo(content),
        hour=ts.hour
    )


def generate_daily_digest(messages: List[Dict], date_str: str) -> DailyDigest:
    """生成一天的摘要"""
    # 1. 分析每条消息
    message_digests = []
    explicit_todos = []
    
    for msg in messages:
        digest = analyze_message(msg)
        message_digests.append(digest)
        
        if digest.is_explicit_todo:
            explicit_todos.append({
                "message_id": digest.message_id,
                "content": digest.content_preview,
                "time": digest.timestamp.strftime('%H:%M'),
                "channel": digest.channel
            })
    
    # 2. 统计主题分布
    topic_distribution = {}
    for md in message_digests:
        topic_distribution[md.topic] = topic_distribution.get(md.topic, 0) + 1
    
    # 3. 统计情绪分布
    emotion_distribution = {}
    for md in message_digests:
        emotion_distribution[md.emotion] = emotion_distribution.get(md.emotion, 0) + 1
    
    # 4. 计算熬夜相关数据
    late_hours = [md.hour for md in message_digests if md.hour >= 23 or md.hour <= 5]
    late_night_flag = len(late_hours) > 0
    
    # 5. 提取关键主题（去重后的）
    key_topics = list(topic_distribution.keys())
    
    return DailyDigest(
        date=date_str,
        generated_at=datetime.now(),
        total_messages=len(message_digests),
        channels=list(set(md.channel for md in message_digests)),
        topic_distribution=topic_distribution,
        emotion_distribution=emotion_distribution,
        message_digests=message_digests,
        explicit_todos=explicit_todos,
        late_night_flag=late_night_flag,
        late_night_hours=late_hours,
        key_topics=key_topics,
        llm_insight=None
    )
