# TeamDesk · 数字班组工作台 — M1 设计文档

## 0. 一句话
给 3-10 人小团队的内部 AI 班组：统一接入大模型 + 企业知识库 + 业务报表，"数字员工"按 SOP 干重复性分析杂活，全程留痕、关键动作人工审批、绩效可看。

对标真实需求形态（实现网挂单）：AI 中控平台（多角色权限/多模型网关/报表 AI 分析/ACOS 诊断等 workflow）、RAG 智能体（对话+知识库+会议纪要+报告生成）。

## 1. 数字员工编制（内置 5 + 1 supervisor）

| 代号 | 员工 | 岗位 JD | 输入 | 输出 | 工具/依赖 | 权限（自主/审批/禁止） |
|---|---|---|---|---|---|---|
| SUP | 调度长·中枢 | 意图识别→选派员工→串联≤2步 | 任意任务 | Run 计划 | LLM classify | — |
| E1 | 阿数·报表分析师 | 报表洞察：趋势/异常/归因 | xlsx/csv | 3-5 条洞察+图表(ECharts option)+风险提示 | pandas+LLM | 自主:分析；审批:对外发送；禁止:修改源数据 |
| E2 | 老查·文档问答官 | 制度/手册问答，必须带出处 | 文本问题(+文档) | 回答+引用片段(章节定位) | RAG(Chroma+bge-small-zh) | 自主:问答；禁止:超纲承诺 |
| E3 | 小纪·纪要秘书 | 会议/长文→纪要+行动项 | md/txt | 纪要+行动项表(事项/负责人/期限) | LLM | 自主:生成纪要；审批:对外分发 |
| E4 | 美句·文案优化师 | Listing/营销文案改写 | 文本 | 优化稿+改动说明 | LLM | 自主:改写；审批:对外发布 |
| E5 | 听风·VOC 舆情员 | 评论/反馈主题聚类 | csv/txt(评论) | TOP-N 主题+占比+代表原声+建议 | 规则聚类+LLM | 自主:汇总；禁止:删除原始记录 |

员工数据结构（Employee 表）：
```
id, code, name, emoji, title, jd, persona(system prompt),
permissions{autonomous[],approval_required[],forbidden[]},
model(默认继承全局, 可单独覆盖), status(standby/active/paused/error),
metrics 由 usage/runs 聚合: 任务数, 成功率, 平均耗时, tokens
```

## 2. 数据模型（SQLite, SQLAlchemy 2.0 async）

```
employee    (id PK, code UQ, name, emoji, title, jd, persona, permissions JSON, model, created_at)
document    (id PK, filename, kind[xlsx|csv|pdf|txt|md], size, rows INT NULL, text_preview, created_at, indexed BOOL)
chunk       (id PK, doc_id FK, seq, content, embedding_ref TEXT(=chroma id))
run         (id PK, title, trigger[source=upload|chat|manual], status[pending|running|waiting_human|completed|error|cancelled],
             created_at, finished_at, parent_id NULL)
step        (id PK, run_id FK, idx, type[employee|approval|condition], employee_id NULL,
             input_summary, output JSON NULL, reasoning TEXT, status[same as run], started_at, finished_at, tokens INT)
approval    (id PK, run_id FK, step_id FK, payload JSON, risk_note, status[pending|approved|rejected], decided_by, decided_at)
usage       (id PK, ts, employee_id NULL(NULL=supervisor), model, tokens_in, tokens_out, cost_est)
```

## 3. SOP 引擎（核心，参考 CrewMeld 状态机）

- Run = 一串 Step 顺序执行；Supervisor 先产出计划（steps[]），引擎逐步驱动
- 状态迁移仅允许：pending→running→(waiting_human)→completed / error / cancelled；非法迁移抛错
- `employee` 步：调对应 agent（见 §4），期间发 `step.thinking`/`step.output` 事件
- `approval` 步：run 置 waiting_human，写 approval 行，SSE 发 `approval.pending`；`POST /api/approvals/{id}/decide` 恢复（approve→续跑；reject→run error(reason=rejected)）
- `condition` 步：读上一步 output JSON 的 flag 决定跳过后续某步（M1 只做"跳过"）
- 断点：run/step 全落库，重启后 waiting_human 的 run 可继续（M1 不要求自动重连执行中步）

## 4. Agent 契约

```python
# backend/app/agents/base.py
@dataclass
class AgentCtx:
    run_id: str; step_id: str; employee: EmployeeRow
    payload: dict          # {kind: "file"|"text", doc_id? , text?, extra?}
    bus: EventBus; llm: LLMClient; rag: RAGStore
class BaseAgent:
    code: str
    async def plan_hint(self, p: dict) -> bool: ...            # 供 supervisor 路由打分（静态规则即可）
    async def execute(self, ctx: AgentCtx) -> AgentResult: ...
@dataclass
class AgentResult:
    output: dict           # 结构化产物: {insights[], chart?: EChartsOption, citations[], ...}
    reasoning: str         # 展示在时间线里的"思路"
    needs_approval: bool = False   # True 时引擎自动追加 approval 步
    approval_payload: dict | None = None
```

各 agent 无 KEY 时的降级：LLM 调用失败/无 key → 规则兜底（pandas 统计直接成洞察；RAG 退化为关键词命中 top3；聚类退化为关键词分桶），并在 reasoning 标注 `[离线模式]`。**没有 API key 也必须完整跑通演示。**

## 5. 事件协议（SSE `/api/events`）

```
{type, run_id?, employee_id?, ts, payload}
type ∈ run.created | run.status
      step.started | step.thinking | step.output | step.done
      approval.pending | approval.decided
      employee.status | usage.tick | doc.indexed
```
前端订阅单通道；任务时间线 = 过滤 run_id 的事件重放。

## 6. API 面

```
GET  /api/employees                 列表(含聚合 metrics)
GET  /api/employees/{code}          详情(permissions/persona/metrics)
GET  /api/runs?limit=30             列表
GET  /api/runs/{id}                 详情: run + steps[](含 reasoning/output) + events[]
POST /api/tasks                     {kind:"file", doc_id} | {kind:"text", text, qa_doc_id?} → 201 {run_id}
GET  /api/documents  / POST /api/documents(upload)  / GET /api/documents/{id}
GET  /api/approvals?status=pending
POST /api/approvals/{id}/decide     {decision:"approve"|"reject", note?}
GET  /api/usage/summary?days=7      per-employee tokens/cost/任务数/成功率 + 趋势
GET  /api/events                    SSE
GET  /api/health
```

## 7. LLM 层（backend/app/llm.py）

- OpenAI 兼容（`openai` sdk，base_url/key/model 走 env：`LLM_BASE_URL, LLM_API_KEY, LLM_MODEL`；默认 deepseek）
- `chat(system, messages, json_mode=False) -> (text, tokens_in, tokens_out)`，自动写 usage
- 无 key/超时/4xx → 抛 LLMUnavailable，agent 走 §4 降级

## 8. RAG（backend/app/rag.py）

- 入库：上传文档 → 切块(~400 字，滑窗 80) → bge-small-zh 嵌入 → Chroma(sqlite 持久化，volume 挂载)
- 检索：top5，返回 (chunk, score, doc_name, seq)；问答 agent 拼引用 `[来源: 文件名#段seq]`
- 预置语料：`data/corpus/退换货政策.txt`、`data/corpus/员工手册节选.txt`（M1 启动自动索引）

## 9. 前端（Vite + React18 + TS + Tailwind + ECharts，暗色"作战室"风）

- 布局：顶栏(产品名 + 模型配置状态徽标 + 离线模式横幅)；左侧导航 4 页
- **班组工作台**（默认页）：
  - 员工状态灯行（头像/岗位/状态/今日任务数，active 时呼吸灯）
  - 右侧实时事件流（SSE，按 run 分组折叠，thinking 打字机效果）
  - 任务发起器：拖文件 或 输入问题
  - **审批浮层**：approval.pending 时右上角弹卡片（员工+动作+risk_note+证据），批/拒
- **员工档案**：卡片墙→点开抽屉（JD/权限矩阵三色表/Persona 只读/绩效曲线）
- **任务看板**：run 列表→时间线回放（step 展开 reasoning + output 渲染：洞察卡片/ECharts 图表/引用高亮/行动项表格）
- **管理驾驶舱**：tokens 花费趋势、per-employee 成功率/耗时、最近 10 条 usage
- 纯前端无登录（demo），端口 8321

## 10. 示例数据（data/make_samples.py 生成, 确定性 seed）

- `ad_report.xlsx`：30 天投放报表（campaign/日期/花费/点击/转化/GMV），内置一个"ACOS 突变"钩子
- `reviews.csv`：200 条评论，预埋 3 个主题（物流慢/包装破损/客服差）+噪声
- `meeting_notes.md`：1 篇部门周会记录（4 个行动项，人名+期限）
- `corpus/*.txt`：RAG 语料（退换货政策/员工手册节选）

## 11. 交付物 & 验收（Definition of Done）

- [ ] `make up` (docker compose: backend:8320 + frontend:8321) 或 `make dev` 本地双进程
- [ ] 五条黄金路径全绿（有 key 与无 key 两种模式）：
  1. 传 ad_report.xlsx → 阿数 → 洞察+ECharts 趋势图+ACOS 突变的风险提示
  2. 问"破损包裹怎么理赔？" → 老查 → 回答+引用片段
  3. 传 reviews.csv → 听风 → TOP3 主题+占比+代表原声
  4. 传 meeting_notes.md → 小纪 → 纪要+行动项表
  5. 阿数输出"对外发送"动作 → 审批浮层 → 批准后 Run 收尾（拒绝则 error=rejected 留痕）
- [ ] 任务看板可逐步回放；驾驶舱有花费/成功率数据
- [ ] README 3 行启动 + 60s GIF + 3 张截图（工作台/时间线/审批）
- [ ] MIT LICENSE

## 12. 分期

- M1（本次）：上述全部最小闭环
- M2：SOP 可视化编排画布（拖拽员工/审批节点）+ 权限矩阵编辑 + 多租户
- M3：知识图谱增强（Kuzu：文档实体→关系图谱检索）+ 员工"成长"（案例沉淀库+复盘周报）
- 二期叙事（卖更高锚）：垂域 LoRA 微调管线接进来（对标实现网 agent 开发单）

## 13. 分工（施工单）

- **A 地基**（backend 基础）：pyproject/config/db/models/bus/llm/rag/sop 引擎/api 全部路由(SSE)/employees/seed/main.py —— 依赖 agent 处先用 fake（返回固定 AgentResult）
- **B 员工**（5 agents + supervisor）：agents/* 实装（含离线降级）
- **C 前端**：frontend 全量（对照 §6/§9 实现，SSE 对接 §5）
- **D 环境与数据**：data/make_samples.py + docker-compose.yml + Dockerfile×2 + Makefile + .env.example + README + LICENSE
- 顺序：A 先行；A 完 → B、C、D 并行；集成/联调/验收由主 agent 负责
