"""占位 Agent（地基自测用；B 工单会用真实实现替换本文件内容）。

行为约定：
- 每个 code 返回固定但结构合理的 AgentResult
- E1（阿数）返回 needs_approval=True 以打通审批 park/resume 链路
- reasoning 一律带 "[占位]" 前缀
"""
from __future__ import annotations

from .base import AgentCtx, AgentResult, BaseAgent


class FakeAgent(BaseAgent):
    def __init__(self, code: str, canned: dict) -> None:
        self.code = code
        self._canned = canned

    async def plan_hint(self, p: dict) -> bool:
        hint = self._canned.get("_hint")
        if not hint:
            return False
        for k, v in hint.items():
            if p.get(k) != v:
                return False
        return True

    async def execute(self, ctx: AgentCtx) -> AgentResult:
        c = self._canned
        return AgentResult(
            output={k: v for k, v in c.items() if not k.startswith("_")},
            reasoning=c.get("_reasoning", "[占位] fake agent 固定输出"),
            needs_approval=bool(c.get("_needs_approval", False)),
            approval_payload=c.get("_approval_payload"),
        )


_FAKE_SPECS: dict[str, dict] = {
    "SUP": {
        "_reasoning": "[占位] supervisor 路由当前由 POST /api/tasks 的启发式承担；LLM 版将由 B 工单实装。",
        "plan_note": "fake supervisor",
    },
    "E1": {
        "_hint": {"kind": "file", "file_kind": "xlsx"},
        "_needs_approval": True,
        "_approval_payload": {"risk_note": "阿数要把分析报表对外发送给管理层（对外发送属审批级动作）",
                              "payload": {"action": "send_external", "recipient": "管理层邮件组"}},
        "_reasoning": "[占位] 读取 30 天投放报表 → 计算 ACOS 逐日趋势 → 检测到第 21 天 ACOS 从 28% 跳到 61%（花费翻倍、GMV 持平）→ 生成洞察与图表 → 触发对外发送审批。",
        "insights": [
            {"level": "info", "text": "近 30 天花费合计 ¥86,400，GMV ¥219,500，综合 ACOS 39.4%"},
            {"level": "warning", "text": "第 21 天起 ACOS 从 28% 突增至 61%，主要因 campaign『夏季大促』花费翻倍而 GMV 持平"},
            {"level": "info", "text": "campaign『常青款-精准』连续 14 天 ACOS 低于 25%，存在加预算空间"},
        ],
        "chart": {
            "title": {"text": "日花费 vs ACOS（近30天）"},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["花费(¥)", "ACOS(%)"]},
            "xAxis": {"type": "category", "data": [f"D{i}" for i in range(1, 31)]},
            "yAxis": [{"type": "value", "name": "花费(¥)"}, {"type": "value", "name": "ACOS(%)", "max": 80}],
            "series": [
                {"name": "花费(¥)", "type": "bar", "data": [2800] * 20 + [5600] * 10},
                {"name": "ACOS(%)", "type": "line", "yAxisIndex": 1,
                 "data": [28, 30, 27, 29, 28, 31, 30, 28, 27, 29, 30, 28, 27, 28, 29, 30, 28, 27, 29, 30, 61, 58, 62, 60, 59, 61, 57, 60, 58, 59]},
            ],
        },
        "risks": [{"level": "high", "text": "『夏季大促』campaign ACOS 持续 >60%，建议暂停或降价 30% 观察 48h"}],
        "send_external": True,
    },
    "E2": {
        "_hint": {"kind": "text", "qa": True},
        "_reasoning": "[占位] 问题向量检索 top5 命中『退换货政策』第 3 段（破损理赔条款）与第 7 段（时限）→ 组织回答并附引用。",
        "answer": "破损包裹理赔分两档：签收时当场验货发现的破损，48 小时内拍照上传即可全额退款+补发；签收后发现的内物破损，7 天内提供开箱视频可申请 50% 赔付或换货。运费均由商家承担，无需买家垫付。",
        "citations": [
            {"doc_name": "退换货政策.txt", "seq": 3, "snippet": "……签收后发现内物破损的，须在 7 日内提交完整开箱视频，平台按订单金额 50% 赔付或安排换货……"},
            {"doc_name": "退换货政策.txt", "seq": 7, "snippet": "……所有售后退货运费由商家承担，买家无需垫付；理赔款项 1-3 个工作日原路退回……"},
        ],
    },
    "E3": {
        "_hint": {"kind": "file", "file_kind": "md"},
        "_reasoning": "[占位] 解析周会记录 → 抽取议题 3 项 → 按『动词+事项+人名+期限』正则提取 4 条行动项 → 生成纪要。",
        "summary": "本周会聚焦 Q3 复盘与 Q4 规划：投放 ROI 达标但库存周转恶化；决定收缩长尾 SKU、加大爆品备货；客服系统选型定于下周三前完成。",
        "topics": ["Q3 经营数据复盘", "库存周转恶化归因", "客服系统选型"],
        "action_items": [
            {"item": "输出长尾 SKU 清仓方案（TOP50 滞销款）", "owner": "阿数", "deadline": "下周二"},
            {"item": "完成客服系统三家供应商 POC 对比", "owner": "老查", "deadline": "下周三"},
            {"item": "更新爆品备货模型参数并回测", "owner": "听风", "deadline": "本周五"},
            {"item": "撰写 Q4 投放预算草案报管理层", "owner": "美句", "deadline": "下周一"},
        ],
    },
    "E4": {
        "_hint": {"kind": "text", "copy": True},
        "_reasoning": "[占位] 按 Listing 五段式重构卖点 → 突出『3 年质保+48h 发货』差异化 → 保留全部合规表述。",
        "original": "很好用的保温杯，保温效果好，推荐购买。",
        "optimized": "【3 年质保】316L 不锈钢内胆，实测 12 小时保温 65℃+；48 小时极速发货，漏液包赔。附赠杯刷与备用密封圈，出差通勤两用。",
        "changes": ["补齐核心参数（材质/保温时长），替换空泛形容词", "前置质保与发货时效两个转化钩子", "增加赠品信息提升客单感知"],
    },
    "E5": {
        "_hint": {"kind": "file", "file_kind": "csv"},
        "_reasoning": "[占位] 200 条评论按关键词分桶（物流/包装/客服/其他）→ 桶内取代表性短句 → 计算占比并给出改进建议。",
        "total_reviews": 200,
        "topics": [
            {"name": "物流慢", "ratio": 0.31, "examples": ["快递 9 天才到，包装都变形了", "说是次日达，实际等了四天", "物流信息两天没更新"]},
            {"name": "包装破损", "ratio": 0.24, "examples": ["盒子瘪了一角，杯子还好", "外箱湿透了，幸好有气柱袋", "盖子运输中裂了一条缝"]},
            {"name": "客服差", "ratio": 0.12, "examples": ["问了三遍没回音", "机器人只会复读，转人工排 40 分钟"]},
        ],
        "advice": ["物流慢占比最高（31%）：建议与承运商谈判时效或切换仓配", "包装破损集中在盖子：建议出厂增加卡扣固定工序"],
    },
}


def build_fakes() -> dict[str, BaseAgent]:
    return {code: FakeAgent(code, spec) for code, spec in _FAKE_SPECS.items()}
