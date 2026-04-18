# AutoResearchClaw 统计建模比赛使用指南

## 📋 已完成的工作

我已为你完成以下调研和配置：

### 1. 比赛约束调研
- ✅ 论文格式：≤16000字符，查重≤20%
- ✅ 论文结构：封面→摘要→目录→图表清单→正文→参考文献→附录→致谢
- ✅ 评分标准：假设合理性、建模创造性、结果正确性、逻辑性、文字表述
- ✅ AI使用规范：需披露，论文需人工审核

### 2. 配置文件
- `config.competition.yaml` - 比赛专用配置
- `prompts.competition.yaml` - 比赛专用提示词

### 3. 模型推荐
- **主模型**：Qwen3-Coder-Next-FP8（256k上下文，代码优化）
- **备选**：Qwen3.5-35B-A3B、GPT-4o-mini

---

## 🚀 快速开始

### Step 1: 安装 AutoResearchClaw

```bash
# 克隆仓库
git clone https://github.com/aiming-lab/AutoResearchClaw.git
cd AutoResearchClaw

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装
pip install -e .

# 初始化
researchclaw setup
researchclaw init
```

### Step 2: 配置 API Key

```bash
# 设置环境变量
export QWEN_API_KEY="your-api-key-here"
```

### Step 3: 修改配置文件

编辑 `config.competition.yaml`：

```yaml
# 修改第12行：填入你的比赛主题
research:
  topic: "你的比赛主题"

# 修改第21行：填入你的API端点
llm:
  base_url: "https://your-endpoint.com/v1"

# 修改第141行：填入你的队名
export:
  authors: "你的队名"
```

### Step 4: 运行

```bash
# 启动研究流程（Co-Pilot模式）
researchclaw run \
  --config config.competition.yaml \
  --topic "你的比赛主题" \
  --mode co-pilot
```

---

## 🎯 关键节点说明

系统会在以下阶段暂停，等待你的确认：

| 阶段 | 内容 | 你的任务 |
|------|------|---------|
| **Stage 7** | 假设生成 | 审核研究假设是否合理 |
| **Stage 9** | 实验设计 | **关键！** 确认数据集选择和基线方法 |
| **Stage 14** | 结果分析 | 审核实验结果，决定继续/优化/转向 |
| **Stage 16** | 论文大纲 | 审核论文结构是否符合比赛要求 |
| **Stage 20** | 质量门控 | 最终检查，确认无误后提交 |

### 常用命令

```bash
# 查看状态
researchclaw status artifacts/rc-xxx

# 批准继续
researchclaw approve artifacts/rc-xxx --message "继续"

# 拒绝并说明原因
researchclaw reject artifacts/rc-xxx --reason "需要调整xxx"

# 添加指导
researchclaw guide artifacts/rc-xxx --stage 9 --message "使用UCI的xx数据集"

# 从检查点恢复
researchclaw run --from-stage 10 --topic "..."
```

---

## 📊 输出文件说明

运行完成后，在 `artifacts/rc-xxx/deliverables/` 目录下：

| 文件 | 用途 |
|------|------|
| `paper_draft.md` | 论文草稿（可直接用于比赛） |
| `paper.tex` | LaTeX版本（可选） |
| `references.bib` | 参考文献 |
| `verification_report.json` | 引用验证报告 |
| `experiment_runs/` | 可运行代码 |
| `charts/` | 结果图表 |
| `reviews.md` | 自评检查清单 |

---

## ⚠️ 重要提醒

### 1. 数据集选择（Stage 9）

系统会自动搜索数据集，但你需要确认：

- ✅ 数据是否公开可获取？
- ✅ 数据规模是否适中（训练时间可控）？
- ✅ 是否有公开基线结果可对比？

**推荐数据集来源**：
- UCI ML Repository
- Kaggle Datasets
- HuggingFace Datasets
- 政府开放数据平台

### 2. AI 使用披露

根据2026年比赛新规，你需要在论文附录中添加：

```
本研究使用AI工具辅助文献检索、代码生成和论文撰写，
所有内容由作者审核修改，作者对论文内容负全部责任。
```

### 3. 查重控制

- 系统已配置避免大段引用
- 生成后建议使用知网查重
- 重复率需控制在20%以内

### 4. 字数控制

- 正文不超过16000字符（计空格）
- 摘要约500字
- 系统会在质量门控阶段检查

---

## 💰 成本预估

| 配置 | 预估成本 | 运行时间 |
|------|---------|---------|
| Qwen3-Coder-Next-FP8 | ¥30-80 | 2-4小时 |
| 含人工协作 | - | 4-8小时（含审核时间） |

---

## 📞 问题排查

| 问题 | 解决方案 |
|------|---------|
| API连接失败 | 检查 `base_url` 和 `api_key` |
| 数据集搜索不到 | 手动指定数据集名称 |
| 实验运行失败 | 检查依赖包是否安装 |
| 论文字数超标 | 在 Stage 16 调整大纲 |

---

## 📚 比赛官网

- 全国大学生统计建模大赛：http://tjjmds.ai-learning.net/

---

**祝比赛顺利！** 🏆
