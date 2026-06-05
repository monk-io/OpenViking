# Trajectory / Experience 经验记忆模块重设计

> 目标：用优秀机器学习框架的术语和分层方式，重新描述并重构 OpenViking 当前 `trajectories` / `experiences` 经验记忆模块，让它从“记忆抽取与写文件”升级为“训练样本采集 → 经验策略训练 → 评估发布 → 推理服务”的闭环。

## 1. 背景

当前 agent memory 主要由两类记忆组成：

| 类型 | 当前含义 | 存储位置 | 更新策略 |
| --- | --- | --- | --- |
| `trajectories` | 从一次 agent 任务执行中抽取出的可复用操作契约 | `viking://user/<user>/memories/trajectories/` | `add_only` |
| `experiences` | 从 trajectory 中蒸馏出的可复用执行经验 | `viking://user/<user>/memories/experiences/` | `upsert` |

核心代码位置：

- `openviking/session/compressor_v2.py`
- `openviking/session/memory/agent_trajectory_context_provider.py`
- `openviking/session/memory/agent_experience_context_provider.py`
- `openviking/prompts/templates/memory/trajectories.yaml`
- `openviking/prompts/templates/memory/experiences.yaml`

当前流程已经具备“样本”和“蒸馏经验”的雏形，但代码与概念仍然主要围绕 memory CRUD 展开。本文建议引入 ML framework 风格的训练/推理术语，使系统边界更清晰，也为后续评估、版本管理、灰度发布和在线学习打基础。

## 2. 当前实现梳理

### 2.1 提交流程中的 agent memory 抽取

`Session.commit()` 后台阶段会并发执行：

```text
archive summary generation
long-term memory extraction
agent memory extraction
```

当 `config.memory.agent_memory_enabled` 开启且 memory extraction 开启时，会调用：

```python
SessionCompressorV2.extract_agent_memories(...)
```

当前 agent memory extraction 是两阶段：

```text
Session messages
  ↓
Phase 1: trajectory extraction
  ↓
new trajectory files
  ↓
Phase 2: experience consolidation
  ↓
experience files + derived_from links
```

### 2.2 Phase 1: trajectory extraction

`AgentTrajectoryContextProvider` 负责暴露 `trajectories` schema，并从 archived conversation 中提取 trajectory。

当前 trajectory schema 的关键字段：

| 字段 | 作用 |
| --- | --- |
| `trajectory_name` | 稳定命名任务边界 |
| `outcome` | `success` / `failure` / `partial` / `unfinished` / `unknown` |
| `retrieval_anchor` | 专用于向量检索的语义锚点 |
| `content` | 可复用操作契约，包含 domain、trigger、preconditions、procedure、anti-patterns 等 |

关键设计：

- `operation_mode: add_only`，保留每次执行样本。
- 文件名包含 session timestamp，降低覆盖风险。
- `embedding_template` 使用 `trajectory_name + retrieval_anchor`，避免把完整长内容直接作为索引文本。

这使 trajectory 更像 ML 里的 **training example / episode / rollout**，而不是最终推理提示。

### 2.3 Phase 2: experience consolidation

`AgentExperienceContextProvider` 针对每条新 trajectory：

1. 使用 `trajectory_summary` 在 experience 目录检索 top-K candidate experiences。
2. 读取候选 experience。
3. 对 top candidates 加载最近的 source trajectories 作为 grounding material。
4. LLM 输出新 experience、同名更新、`supersedes` 替换或 skip。
5. 系统将 experience 与 trajectory 写入 `derived_from` link。

当前 experience 的格式为：

```md
## Situation
- ...

## Approach
- ...

## Reflect
- ...
```

这使 experience 更像 ML 系统中的 **distilled policy / policy card / inference hint**。

### 2.4 Lineage

当前系统会维护：

```text
experience --derived_from--> trajectory
trajectory <--backlink-- experience
```

这已经是很重要的 lineage 基础：experience 不再只是孤立总结，而是可以追溯到训练样本。

## 3. 当前设计的优点

### 3.1 样本与策略分离

当前 `trajectory` 与 `experience` 的分离是正确方向：

```text
trajectory = 一次执行样本
experience = 从多个样本中蒸馏出的策略
```

这类似：

```text
dataset example → learned rule / policy
```

### 3.2 trajectory add-only，适合审计和回放

`trajectories` 不覆盖历史，适合作为：

- 训练数据
- 回放数据
- debug 数据
- experience 的 provenance

### 3.3 experience upsert，适合持续学习

`experiences` 可以同名更新，也可以通过 `supersedes` 替换更窄的旧经验，符合在线学习和经验蒸馏的方向。

### 3.4 有系统维护的 lineage

`derived_from` link 为后续做质量评估、回滚、血缘追踪、经验置信度统计打下基础。

## 4. 当前主要问题

### 4.1 术语仍偏 memory CRUD

当前名称如：

```text
extract_agent_memories
AgentTrajectoryContextProvider
AgentExperienceContextProvider
apply_operations
```

这些术语更像“抽取记忆并写入文件”，没有体现“从执行轨迹训练经验策略”的学习系统语义。

### 4.2 training / inference 边界不清晰

当前 commit 后立即执行：

```text
extract trajectory → consolidate experience → write memory
```

这把以下阶段混在一起：

- 数据采集
- 样本构造
- 经验训练
- 经验发布
- 经验推理召回

缺少 ML framework 中常见的：

- `Dataset`
- `DataLoader`
- `Trainer`
- `Evaluator`
- `Registry`
- `Serving Engine`

### 4.3 experience 缺少版本、状态和指标

当前 experience 主要靠 `experience_name` 定位，缺少：

- `experience_id`
- `version`
- `status`
- `support_count`
- `success_rate`
- `confidence`
- `last_trained_at`
- `source_trajectory_count`

后果：

- rename / supersedes 语义比较脆弱。
- 好经验和坏经验没有显式区分。
- 不能灰度发布或回滚。
- 推理时难以按质量排序。

### 4.4 训练后缺少显式 eval / gate

当前 LLM 生成的 experience 基本直接进入可召回状态，缺少：

- 格式校验
- 适用边界校验
- 冲突检测
- 过泛化检测
- 经验质量评分
- 基于历史 trajectory 的 replay 验证

### 4.5 推理侧仍依赖通用 memory retrieval

推理时主要依赖 generic memory retrieval，没有显式区分：

```text
用户偏好 memory
事实 memory
trajectory 样本
experience policy
```

理想情况下，推理应优先召回 `ExperiencePolicy`，只有需要 debug / provenance / 低置信度解释时才加载 source trajectory。

## 5. 推荐术语体系

建议把当前 traj/exp 体系映射为 ML framework 风格的术语：

| 当前概念 | 推荐术语 | 类比 ML 框架 |
| --- | --- | --- |
| session archive | `RunLog` / `TraceLog` | 原始训练日志 |
| trajectory | `Episode` / `TrajectoryExample` | 训练样本、rollout |
| trajectories directory | `ReplayBuffer` / `TrajectoryDataset` | 经验回放池 |
| experience | `ExperiencePolicy` / `PolicyCard` | 蒸馏后的策略 |
| experience consolidation | `ExperienceTrainer.fit()` | 训练 / 蒸馏 |
| candidate experiences | `NearestPolicyBatch` | 训练 batch / support candidates |
| source trajectories | `SupportSet` | 支撑样本 |
| supersedes | `Policy Version Upgrade` | 模型版本替换 |
| derived_from links | `LineageGraph` | 模型血缘 |
| retrieval injection | `ExperienceServing` | 推理服务 |
| commit extraction | `online_train_on_commit()` | 在线训练 |

推荐核心命名：

```text
Trajectory       → TrajectoryExample / Episode
Experience       → ExperiencePolicy
Agent Extraction → Experience Learning
Experience Recall → Experience Serving
```

## 6. 训练机制重设计

### 6.1 总体训练链路

```text
RunLog
  ↓
EpisodeBuilder
  ↓
TrajectoryDataset / ReplayBuffer
  ↓
ExperienceTrainer
  ↓
ExperienceEvaluator
  ↓
ExperienceRegistry
  ↓
Production ExperiencePolicy
```

### 6.2 EpisodeBuilder

对应当前 `AgentTrajectoryContextProvider`。

职责：从一次 archived conversation / run log 中构造一个或多个结构化训练样本。

建议接口：

```python
class EpisodeBuilder:
    async def build(self, run_log: RunLog) -> list[TrajectoryExample]:
        ...
```

建议输出结构：

```json
{
  "trajectory_id": "traj_xxx",
  "task_signature": "cancel_booking_with_policy_check",
  "domain": "airline",
  "intent": "cancel existing booking",
  "state": "generalized state before action",
  "actions": [
    {
      "tool": "search_booking",
      "input_schema": "generalized input",
      "observation": "generalized observation"
    },
    {
      "tool": "cancel_booking",
      "input_schema": "generalized input",
      "observation": "generalized observation"
    }
  ],
  "outcome": "success",
  "reward": 1.0,
  "failure_modes": [],
  "retrieval_anchor": "positive retrieval anchor",
  "source_session": "viking://session/...",
  "created_at": "..."
}
```

重点：trajectory 应从“markdown 经验”升级为“可训练样本”。

### 6.3 TrajectoryDataset / ReplayBuffer

对应当前 trajectory 目录。

它不只是文件夹，而应该被视为训练数据集，支持：

- 按 intent / domain / tool sequence 检索。
- 按 outcome 过滤。
- 按失败样本采样。
- 按新鲜度采样。
- 按 source experience 反查。
- 为 ExperienceTrainer 提供 support set。

建议抽象：

```python
class TrajectoryDataset:
    async def add(self, examples: list[TrajectoryExample]) -> None:
        ...

    async def sample_support_set(
        self,
        task_signature: str,
        *,
        top_k: int,
        include_failures: bool = True,
    ) -> list[TrajectoryExample]:
        ...
```

### 6.4 ExperienceTrainer

对应当前 `AgentExperienceContextProvider`。

职责：从新 trajectory 与相关历史经验中蒸馏出 experience policy candidate。

建议接口：

```python
class ExperienceTrainer:
    async def fit(
        self,
        new_examples: list[TrajectoryExample],
        support_policies: list[ExperiencePolicy],
        support_examples: list[TrajectoryExample],
    ) -> list[ExperiencePolicyCandidate]:
        ...
```

训练输入建议包含：

```text
new trajectory examples
+ nearest existing policies
+ source trajectories of those policies
+ negative / failed trajectories
+ current registry metadata
```

这样 experience 不是简单总结单条 trajectory，而是从数据中学习出的可复用策略。

### 6.5 ExperienceEvaluator

训练后不要直接发布，应增加 evaluator。

建议接口：

```python
class ExperienceEvaluator:
    async def evaluate(
        self,
        candidate: ExperiencePolicyCandidate,
    ) -> EvalReport:
        ...
```

建议 gate：

#### 6.5.1 Schema Gate

- 必须包含 `Situation` / `Approach` / `Reflect`。
- heading 顺序固定。
- 每个 section 使用 bullet。
- `Approach` 不超过约定长度。

#### 6.5.2 Atomic Scope Gate

- 一个 experience 只覆盖一个 user intent。
- 不把多个工具目标、生命周期变化或写字段来源混成一个 experience。

#### 6.5.3 Specificity Gate

- 防止过泛化。
- 防止把某个具体 case 直接写成普适规则。

#### 6.5.4 Privacy / Abstraction Gate

- 不保留 raw id、姓名、联系方式、金额、日期、地点、路径等实例局部信息。
- 使用抽象占位描述。

#### 6.5.5 Conflict Gate

- 检查是否与已有 production policy 冲突。
- 若冲突，进入 staging 或要求 supersedes。

#### 6.5.6 Lineage Gate

- 至少关联一个 source trajectory。
- 如果 supersedes 旧 policy，应继承旧 policy 的 source trajectories。

#### 6.5.7 Quality Score

根据以下信号计算 confidence：

- 成功 trajectory 数量。
- 失败 trajectory 数量。
- 同类任务召回后的成功率。
- 最近是否被用户纠正。
- 是否有工具错误。

### 6.6 ExperienceRegistry

当前 experience 写入即生产。建议引入 registry 语义：

```text
candidate → staging → production → deprecated
```

experience metadata 建议：

```json
{
  "experience_id": "exp_xxx",
  "experience_name": "booking_duplicate_handling",
  "version": 3,
  "status": "production",
  "task_signature": "booking_duplicate_handling",
  "confidence": 0.82,
  "support_count": 12,
  "success_count": 10,
  "failure_count": 2,
  "source_trajectory_ids": ["traj_1", "traj_2"],
  "supersedes_ids": ["exp_old"],
  "trained_at": "...",
  "last_served_at": "...",
  "served_count": 42
}
```

## 7. 推理机制重设计

### 7.1 总体推理链路

```text
User Task
  ↓
TaskSpecParser
  ↓
ExperienceRetriever
  ↓
ExperienceReranker
  ↓
PromptCompiler
  ↓
Agent Execution
  ↓
RuntimeObserver
  ↓
New Training Example
```

### 7.2 TaskSpecParser

不要直接拿用户 query 搜 memory。先解析任务规格：

```json
{
  "domain": "travel",
  "intent": "change existing booking",
  "operation_family": "update_existing_object",
  "tools_needed": ["booking_search", "booking_update"],
  "risk_level": "state_changing"
}
```

这一步输出的 task spec 可同时用于：

- experience retrieval query。
- rerank feature。
- prompt compiling。
- execution observer 对齐。

### 7.3 ExperienceRetriever

推理时应优先检索 `ExperiencePolicy`，而不是所有 memory 混检。

推荐层级：

```text
Level 1: production ExperiencePolicy
Level 2: related source TrajectoryExamples
Level 3: raw session archive, only for debug / explanation
```

默认只注入 Level 1。只有以下场景才加载 trajectory：

- 用户要求解释来源。
- policy confidence 较低。
- retrieved policies 之间冲突。
- agent 需要 debug 历史失败样本。

### 7.4 ExperienceReranker

排序不应只靠向量相似度，应融合更多 policy quality signals：

```text
final_score =
  semantic_score
  + applicability_score
  + confidence
  + success_rate
  + freshness
  - conflict_penalty
  - overgeneralization_penalty
```

候选特征：

| 特征 | 含义 |
| --- | --- |
| `semantic_score` | query 与 experience 的向量相似度 |
| `applicability_score` | task spec 与 Situation / boundary 的匹配度 |
| `confidence` | 训练与运行反馈得到的经验置信度 |
| `success_rate` | 该 experience 被召回后的历史成功率 |
| `freshness` | 最近训练或使用时间 |
| `conflict_penalty` | 与其他 policy 冲突时降权 |
| `overgeneralization_penalty` | 过泛经验降权 |

### 7.5 PromptCompiler

将召回的 experience 编译成推理 prompt。

示例：

```md
## Retrieved Experience Policies

### Policy: booking_duplicate_handling
- Confidence: high
- Applies when:
  - User asks to handle a potentially duplicated booking.
- Do:
  - First verify existing booking state.
  - If duplicate is confirmed, compare object ownership and policy constraints.
  - Only perform state-changing action after confirmation.
- Do not:
  - Never cancel or overwrite a booking based only on user wording.
- Source:
  - Derived from multiple successful trajectories.
```

注意：

- 推理 prompt 注入的是 concise policy，不是长 trajectory。
- `Approach` 应作为执行逻辑。
- `Reflect` 应作为 guardrail。
- source trajectory 默认只显示 summary / count，不展开原文。

### 7.6 RuntimeObserver

每次 experience 被召回和使用后，记录使用反馈：

```json
{
  "experience_id": "exp_xxx",
  "served_for_task": "...",
  "was_used": true,
  "outcome": "success",
  "user_correction": false,
  "tool_error": false
}
```

这些反馈会进入下一轮训练，形成 online learning loop。

## 8. 推荐模块划分

### 8.1 学习侧模块

```text
openviking/session/experience_learning/
  ├── engine.py              # ExperienceLearningEngine
  ├── episode_builder.py     # EpisodeBuilder
  ├── dataset.py             # TrajectoryDataset / ReplayBuffer
  ├── trainer.py             # ExperienceTrainer
  ├── evaluator.py           # ExperienceEvaluator
  ├── registry.py            # ExperienceRegistry
  └── lineage.py             # LineageTracker
```

核心入口：

```python
class ExperienceLearningEngine:
    async def train_on_commit(...):
        examples = await EpisodeBuilder(...).build(run_log)
        await TrajectoryDataset(...).add(examples)

        support = await TrajectoryDataset(...).sample_support_set(...)
        candidates = await ExperienceTrainer(...).fit(examples, support)
        reports = await ExperienceEvaluator(...).evaluate_many(candidates)
        await ExperienceRegistry(...).publish_approved(candidates, reports)
```

### 8.2 推理侧模块

```text
openviking/retrieve/experience_serving/
  ├── task_spec.py           # TaskSpecParser
  ├── retriever.py           # ExperienceRetriever
  ├── reranker.py            # ExperienceReranker
  ├── compiler.py            # ExperiencePromptCompiler
  └── observer.py            # ExperienceUsageObserver
```

核心入口：

```python
class ExperienceServingEngine:
    async def retrieve_for_task(...):
        task_spec = await TaskSpecParser(...).parse(messages, current_task)
        candidates = await ExperienceRetriever(...).retrieve(task_spec)
        ranked = await ExperienceReranker(...).rank(task_spec, candidates)
        prompt_block = ExperiencePromptCompiler(...).compile(ranked)
        return prompt_block
```

## 9. 数据模型建议

### 9.1 TrajectoryExample

可以在现有 `trajectories.yaml` 基础上逐步补充字段：

```yaml
fields:
  - trajectory_id
  - task_signature
  - domain
  - intent
  - operation_family
  - tool_sequence
  - outcome
  - reward
  - failure_modes
  - retrieval_anchor
  - content
  - source_session_uri
  - created_at
```

兼容策略：

- 初期保留现有字段。
- 新字段作为 metadata 附加。
- `embedding_template` 继续使用短文本：`task_signature + retrieval_anchor`。

### 9.2 ExperiencePolicy

可以在现有 `experiences.yaml` 基础上补充 metadata：

```yaml
fields:
  - experience_id
  - experience_name
  - version
  - status
  - task_signature
  - confidence
  - support_count
  - success_count
  - failure_count
  - content
  - supersedes
  - trained_at
  - last_served_at
  - served_count
```

其中 `content` 继续保持：

```md
## Situation
...

## Approach
...

## Reflect
...
```

## 10. 最小落地路线

### Step 1: 术语层重构，不动存储格式

目标：让代码语义先对齐学习系统。

- 新增 wrapper：
  - `ExperienceLearningEngine`
  - `EpisodeBuilder`
  - `ExperienceTrainer`
  - `LineageTracker`
- 内部仍调用现有 provider 和 `extract_agent_memories` 逻辑。
- 不迁移现有文件。

### Step 2: 增加 registry metadata

目标：让 experience 从普通 memory file 升级为可发布策略。

新增 metadata：

```text
experience_id
version
status
confidence
support_count
success_count
failure_count
trained_at
source_trajectory_count
```

### Step 3: 增加 Evaluator / Gate

目标：减少坏经验直接进入推理。

先做 deterministic gate：

- 格式检查。
- atomic scope 检查。
- source trajectory 检查。
- 具体实体脱敏检查。
- `Approach` 长度检查。
- conflict / supersedes 检查。

### Step 4: 推理侧显式 Experience Serving

目标：推理阶段显式召回 `ExperiencePolicy`。

新增链路：

```text
task → experience policy retrieval → rerank → prompt compile
```

并与 generic memory retrieval 区分开。

### Step 5: 使用反馈闭环

目标：让经验质量随使用反馈持续更新。

记录：

- experience 是否被召回。
- 是否被 agent 实际使用。
- 任务结果是否成功。
- 是否出现用户纠正。
- 是否出现工具错误。

## 11. 与现有实现的兼容方案

### 11.1 保持存储路径不变

短期不修改：

```text
viking://user/<user>/memories/trajectories/
viking://user/<user>/memories/experiences/
```

只在代码中引入更清晰的抽象层。

### 11.2 保持 schema 向后兼容

新字段尽量放入 `MEMORY_FIELDS` metadata，不破坏现有 markdown 内容。

### 11.3 保持 `derived_from` link

现有 `derived_from` link 继续作为 lineage 的底层实现。

未来可以在其上封装：

```python
LineageTracker.link_policy_to_examples(policy_uri, trajectory_uris)
```

### 11.4 逐步替换命名

第一阶段保留旧类，新增新类包装：

```text
AgentTrajectoryContextProvider → EpisodeBuilder 内部使用
AgentExperienceContextProvider → ExperienceTrainer 内部使用
```

这样避免大规模破坏现有测试。

## 12. 推荐的最终概念模型

一句话：

> 将 `trajectory` 视为 agent 执行产生的训练样本，将 `experience` 视为从样本中蒸馏并发布的推理策略。

最终系统可以命名为：

```text
OpenViking Experience Learning System
```

核心对象：

| 对象 | 含义 |
| --- | --- |
| `RunLog` | 原始会话日志 |
| `TrajectoryExample` / `Episode` | 训练样本 |
| `ReplayBuffer` | 样本池 |
| `ExperiencePolicy` | 蒸馏后的经验策略 |
| `ExperienceTrainer` | 训练器 |
| `ExperienceEvaluator` | 评估器 |
| `ExperienceRegistry` | 策略注册表 |
| `ExperienceServing` | 推理召回与注入 |
| `LineageGraph` | 样本到策略的血缘 |

目标是把经验记忆模块从：

```text
memory extraction + file upsert
```

升级为：

```text
online experience learning + policy serving
```
