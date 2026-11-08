#!/usr/bin/env python3
"""生成 TeamDesk 演示样例数据（PLAN §10，确定性 seed，幂等：重复运行结果一致）。

产物（相对项目根 teamdesk/data/）：
- ad_report.xlsx        30 天 × 3 campaign 投放报表，19-21 天 ACOS 28%→55% 钩子
- reviews.csv           200 条中文评论，预埋 3 主题（物流慢/包装破损/客服差）+噪声
- meeting_notes.md      部门周会记录，4 个行动项（人名+期限）
- corpus/退换货政策.txt   RAG 语料（可被"破损包裹怎么理赔"命中）
- corpus/员工手册节选.txt  RAG 语料

corpus 同步到 backend/data/corpus/（后端启动时自动索引）。
运行方式（在 teamdesk/ 下）：make sample  或  cd backend && uv run python ../data/make_samples.py
"""
from __future__ import annotations

import csv
import os
import random
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CORPUS_SRC = os.path.join(DATA, "corpus")
CORPUS_DST = os.path.join(ROOT, "backend", "data", "corpus")

SEED = 20261108
START_DATE = date(2026, 10, 1)          # 30 天：10-01 ~ 10-30
SPIKE_DAYS = (19, 20, 21)               # 第 19-21 天 ACOS 突变
rng = random.Random(SEED)

CAMPAIGNS = [
    # (campaign, 基准日GMV, 基准ACOS, CPC, 客单价)
    ("夏季大促", 9200, 0.28, 1.15, 189),
    ("常青款-精准", 5300, 0.22, 1.35, 259),
    ("新品-广泛", 3100, 0.34, 0.95, 139),
]


# ---------------------------------------------------------------- ad_report.xlsx
def make_ad_report(path: str) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ad_daily"
    ws.append(["date", "campaign", "spend_yuan", "clicks", "conversions", "gmv_yuan", "acos_pct"])
    for day in range(1, 31):
        d = START_DATE + timedelta(days=day - 1)
        for name, base_gmv, base_acos, cpc, aov in CAMPAIGNS:
            gmv = round(base_gmv * rng.uniform(0.88, 1.15))
            acos = base_acos + rng.uniform(-0.02, 0.03)
            if name == "夏季大促" and day in SPIKE_DAYS:
                acos = 0.55 + rng.uniform(-0.01, 0.02)   # GMV 持平、花费近翻倍
            elif name == "夏季大促" and day > 21:
                acos = 0.44 + rng.uniform(-0.02, 0.03)   # 尖峰后回落但仍偏高
            spend = round(gmv * acos)
            clicks = max(1, round(spend / cpc))
            conversions = max(0, round(spend / aov * 0.92))  # 下单量近似：花费/客单价
            ws.append([d.isoformat(), name, spend, clicks, conversions, gmv,
                       round(acos * 100, 1)])
    wb.save(path)


# ------------------------------------------------------------------ reviews.csv
_LOGISTICS = [
    "快递9天才到，包装都变形了", "说是次日达，实际等了四天", "物流信息两天没更新",
    "下单一周还在转运中心", "发货慢，催了三次才发出", "包裹在中转站压了五天",
    "双11囤的货，到现在才到一半", "物流一直显示揽收，没下文了", "偏远地区等了十一天",
    "快递丢了一次，补发又等了一周", "运输太慢了，错过使用时间", "物流时效不稳定，这次等了六天",
]
_PACKAGING = [
    "盒子瘪了一角，杯子还好", "外箱湿透了，幸好有气柱袋", "盖子运输中裂了一条缝",
    "开箱发现内托碎了，商品划伤", "泡沫包装太薄，明显保护不够", "箱子被压塌半边",
    "密封贴是撕开的状态收到的", "包装简陋，就一层气泡膜", "收到时瓶身有磕碰掉漆",
    "彩盒印刷歪了，边角全毛糙", "配件袋子破了散了一桌", "外包装完好但内件撞开了卡扣",
]
_SERVICE = [
    "问了三遍没回音", "机器人只会复读，转人工排40分钟", "客服态度差，说话阴阳怪气",
    "半夜找客服根本找不到人", "承诺的补偿拖了一周才兑现", "换货流程繁琐，来回折腾五次",
    "售后踢皮球，物流和平台互相推", "工单提交三天没人处理", "客服只会发标准话术，解决不了问题",
    "退款进度查了半天不给准信", "投诉后态度才变好，一开始爱答不理", "说明书都没有，问了也不解答",
]
_NOISE_POS = [
    "非常好用，第二次回购了", "颜值在线，朋友问的链接", "发货快，隔天就到了，满意",
    "质量超预期，这个价位很值", "包装严实，一点损伤没有", "客服回复及时，处理很爽快",
    "用起来很顺手，推荐购买", "送给妈妈的礼物，她很喜欢", "第二次购买了，一如既往的好",
    "性价比很高，细节做工不错", "物流很快包装也好，好评", "用了半个月，没有问题",
    "颜色比图片还好看", "安装简单，十分钟搞定", "老顾客了，品质稳定",
]
_NOISE_NEG = [
    "颜色和图片有色差", "按键有点松动", "续航没有宣传的那么久",
    "说明书字太小", "重量偏沉，单手拿着累", "气味有点大，晾了两天才好",
    "尺寸买小了，退换麻烦", "接口是老的，不太方便", "价格降得快，买贵了心疼",
]


def make_reviews(path: str) -> None:
    rng2 = random.Random(SEED + 1)
    n_log = 62      # 31%
    n_pkg = 48      # 24%
    n_svc = 24      # 12%
    n_noise = 200 - n_log - n_pkg - n_svc   # 33%（正负混合）
    rows = []
    for _ in range(n_log):
        rows.append(("物流", _pick(_LOGISTICS, rng2), rng2.choice([1, 1, 2, 2, 3])))
    for _ in range(n_pkg):
        rows.append(("包装", _pick(_PACKAGING, rng2), rng2.choice([1, 1, 2, 2, 3])))
    for _ in range(n_svc):
        rows.append(("客服", _pick(_SERVICE, rng2), rng2.choice([1, 1, 2, 2])))
    for i in range(n_noise):
        pos = i % 5 != 0  # 约 80% 正面噪声
        pool = _NOISE_POS if pos else _NOISE_NEG
        rows.append(("noise", _pick(pool, rng2), rng2.choice([4, 5, 5]) if pos else rng2.choice([2, 3, 3])))
    rng2.shuffle(rows)
    start = START_DATE + timedelta(days=5)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "content", "rating"])
        for i, (_, content, rating) in enumerate(rows, 1):
            d = start + timedelta(days=rng2.randrange(0, 25))
            w.writerow([f"R{10000 + i}", d.isoformat(), content, rating])


def _pick(pool: list[str], r: random.Random) -> str:
    return r.choice(pool)


# -------------------------------------------------------------- meeting_notes.md
MEETING_MD = """# 供应链与增长周会纪要（2026-10-26）

**参会**：阿数、老查、听风、美句、王总监
**主持**：王总监　**记录**：小纪（数字员工代记）

## 一、Q3 经营数据复盘（阿数）
- 综合 ACOS 39.4%，达成季度目标（≤40%），但结构失衡：
  - "夏季大促" campaign 后半月 ACOS 从 28% 拉到 55%，吃掉整组利润；
  - "常青款-精准" 连续 14 天 ACOS < 25%，预算反而最保守。
- 结论：**问题不在总量在结构**，预算要在 campaign 之间重新分配。

## 二、库存周转恶化归因（听风）
- 库存周转天数从 38 天升至 52 天，主因 TOP50 滞销 SKU 占用了 31% 仓储位。
- 评论侧印证：物流慢相关差评占 31%，与华东仓爆仓、承运商时效下滑一致。
- 决定：收缩长尾 SKU，Q4 集中备货到 20 个爆品。

## 三、客服系统选型（老查）
- 三家候选（A/B/C）POC 材料已收齐，对比维度：工单闭环时长、知识库命中率、API 开放度。
- 下周三前出对比结论，优先看"知识库命中率 ≥ 85%"这一硬门槛。

## 四、行动项

| # | 事项 | 负责人 | 期限 |
|---|------|--------|------|
| 1 | 输出长尾 SKU 清仓方案（TOP50 滞销款，含折价/捆绑/退仓三档） | 阿数 | 下周二 |
| 2 | 完成客服系统三家供应商 POC 对比，输出结论与推荐理由 | 老查 | 下周三 |
| 3 | 更新爆品备货模型参数并用 Q3 数据回测 | 听风 | 本周五 |
| 4 | 撰写 Q4 投放预算草案（含 campaign 间预算再分配方案）报管理层 | 美句 | 下周一 |

## 五、其他
- "夏季大促" ACOS 异常已于 10-21 当天关停超投计划，复盘报告随行动项 4 一并提交。
- 下次周会：2026-11-02（周一）10:00。
"""


# --------------------------------------------------------------------- corpus
POLICY_TXT = """退换货政策（节选 v3.2，2026-08 生效）

第一章 总则
本政策适用于平台全部自营及入驻商家的实物商品订单。买家在签收后对商品有异议的，可依据本章及后续条款申请退款、换货或赔付。所有售后退货运费由商家承担，买家无需垫付；理赔款项在双方确认方案后 1-3 个工作日原路退回。

第二章 退货
第一条 无理由退货：自签收之日起 7 日内，商品未拆封且不影响二次销售的，买家可申请无理由退货，商家应在 48 小时内响应。
第二条 质量问题退货：经客服核实属于生产缺陷或到货即损的，支持 15 日内退货退款，商家需在 24 小时内上门取件或提供就近驿站取件码。
第三条 拆封不退类目：贴身衣物、食品、已激活电子配件不支持无理由退货，但出现质量问题仍适用第二条。

第三章 换货与补发
第四条 换货：商品存在规格错误、少件、功能异常时，买家可在签收后 15 日内申请换货，商家承担双向运费。
第五条 补发：物流环节导致的丢件、错发，商家应在确认异常后 48 小时内免费补发同款商品，并主动告知新的运单号。
第六条 缺货处理：因商家缺货无法履约的，应全额退款并按订单金额的 10% 支付优惠券补偿。

第四章 破损理赔（重点条款）
第七条 签收当场破损：买家在快递员在场情况下开箱验货，发现外包装变形、渗漏、破损的，可当场拒签；已签收但签收时已发现破损的，须在 48 小时内拍摄商品与外包装照片上传售后通道，商家应予全额退款并免费补发。
第八条 内物破损：签收后发现内物破损的，须在 7 日内提交完整开箱视频（需连续录制、含物流面单特写），平台按订单金额 50% 赔付或安排换货，二者由买家任选。
第九条 运输责任认定：破损理赔责任默认由承运商承担，商家赔付买家后凭开箱证据向承运商追偿；买家无需参与责任认定流程。

第五章 时限与争议
第十条 商家应在买家提交售后申请后 24 小时内首次响应，72 小时内给出处理方案；超时未响应视为同意买家诉求。
第十一条 买卖双方无法达成一致时，可向平台申诉，平台在 3 个工作日内出具裁决；重大争议（单笔金额超过 5000 元）由客服专家组复核。
"""

HANDBOOK_TXT = """员工手册节选（v5.0，2026-06 修订）——远程协作与信息安全篇

一、工作时间与考勤
1. 实行弹性工作制，核心在线时间为每日 10:00-12:00 与 14:00-18:00，周会固定周一 10:00。
2. 月度累计工时不低于 168 小时，加班需在内部系统登记并经直属负责人确认，按 1.5 倍折算调休。
3. 远程办公期间请假须提前 24 小时在系统中提交，紧急事假可口头报备并于当日补录。

二、远程协作规范
4. 所有工作任务必须在项目管理系统中建卡跟踪，禁止仅在聊天记录中流转需求；关键决策须沉淀为文档并归档到部门知识库。
5. 代码提交遵循"小步快跑"原则，单个提交应可独立编译通过；涉及主干合入需至少一名同事完成评审。
6. 线上故障响应：P0 级故障 15 分钟内到岗处理，事后 48 小时内提交复盘报告；隐瞒或延迟上报故障按三级违规处理。
7. 数字员工（自动化 Agent）产出的对外内容，必须由一名人类员工署名复核后方可发出。

三、信息安全
8. 客户数据仅限业务必需范围内访问，任何导出数据必须加密存储，禁止将客户信息用于非业务用途或带离公司环境。
9. 生产环境密钥统一托管于公司密钥管理系统，禁止写入代码仓库、文档或个人笔记；离职或转岗当日自动回收权限。
10. 发现数据泄露或可疑访问，应立即报告安全团队，任何人不得私自删除日志或掩盖痕迹。
11. 违反本章条款视情节给予绩效扣减、解除合同处理；造成损失的，公司保留依法追偿的权利。

四、报销与福利
12. 差旅报销须在行程结束后 10 个工作日内提交，单笔超过 2000 元的支出需事前审批。
13. 年度体检、家庭保险补贴按职级标准发放，具体标准见附录 B。

五、会议与汇报规范
14. 各类会议须指定记录人，纪要在会后 24 小时内发布并同步全体参会人；行动项必须有明确负责人与期限，下周会议逐项复核闭环情况。
15. 跨部门事项需拉齐口径后再同步上级，避免多头汇报；同一事项一周内重复升级的，由发起方承担沟通成本评估。
16. 数据类汇报必须以系统导出的口径为准，引用外部数据须注明来源与截止时间；数字口径冲突时以财务系统为准。
"""


def make_corpus() -> None:
    os.makedirs(CORPUS_SRC, exist_ok=True)
    os.makedirs(CORPUS_DST, exist_ok=True)
    files = {"退换货政策.txt": POLICY_TXT, "员工手册节选.txt": HANDBOOK_TXT}
    for fn, content in files.items():
        src = os.path.join(CORPUS_SRC, fn)
        dst = os.path.join(CORPUS_DST, fn)
        with open(src, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
        with open(dst, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
    # 清理旧的自测语料（不属于交付样例）
    legacy = os.path.join(CORPUS_SRC, "_selftest_policy.txt")
    if os.path.exists(legacy):
        os.remove(legacy)
    legacy_db = os.path.join(CORPUS_DST, "_selftest_policy.txt")
    if os.path.exists(legacy_db):
        os.remove(legacy_db)


# ----------------------------------------------------------------------- main
def main() -> None:
    os.makedirs(DATA, exist_ok=True)
    make_ad_report(os.path.join(DATA, "ad_report.xlsx"))
    make_reviews(os.path.join(DATA, "reviews.csv"))
    with open(os.path.join(DATA, "meeting_notes.md"), "w", encoding="utf-8") as f:
        f.write(MEETING_MD.strip() + "\n")
    make_corpus()

    # 自检
    assert os.path.getsize(os.path.join(DATA, "ad_report.xlsx")) > 0
    with open(os.path.join(DATA, "reviews.csv"), encoding="utf-8") as f:
        n = sum(1 for _ in f) - 1
    assert n == 200, f"reviews.csv rows={n}, expect 200"
    pol = open(os.path.join(CORPUS_SRC, "退换货政策.txt"), encoding="utf-8").read()
    hand = open(os.path.join(CORPUS_SRC, "员工手册节选.txt"), encoding="utf-8").read()
    assert len(pol) >= 800 and len(hand) >= 800, "corpus too short"
    assert "破损" in pol and "开箱视频" in pol, "corpus must answer 破损包裹理赔"
    assert os.path.isfile(os.path.join(CORPUS_DST, "退换货政策.txt")), "corpus not synced"
    print(f"OK: data/ 4 样例 + 2 corpus 生成完毕（seed={SEED}, 30 天 x 3 campaign, 评论 200 条）")
    print("    corpus 已同步 backend/data/corpus/")


if __name__ == "__main__":
    main()
