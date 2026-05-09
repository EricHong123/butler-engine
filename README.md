# 🏛️ Butler Engine

> 高净值私人 AI 管家 — 家族专属 AI 私享服务

Butler Engine 是一个完整的 AI Agent 服务系统，专为高净值家族提供私有化、专属定制的数字化管家服务。覆盖资产管理、税务规划、文档保险库、日程统筹、子女教育、健康管理等家族核心需求。

---

## 架构总览

```
客户微信 → 企业微信 Bot → FastAPI → AgentRunner → LLM (DeepSeek/Claude/...)
                                    ↓
                              审核队列 → 人工审核 → 发送
                                    ↓
                              PostgreSQL (conversations, audit_logs, assets...)
```

---

## 功能清单

### 核心引擎
- **Agent 运行时**：Python 移植 Claude Code 架构 — `AgentRunner` + `agent_loop` + Tool 系统
- **7 个专业 Agent**：管家助理、财富顾问、税务策略师、文档秘书、日程管家、教育顾问、健康顾问
- **6 个专属工具**：`query_assets`、`check_tax_calendar`、`search_docs`、`schedule_event`、`generate_report`、`escalate_to_human`
- **Agent Switch**：对话中一键切换 Agent，每个 Agent 独立 system prompt + 工具集

### 企业微信集成
- AES-256-CBC 消息加密/解密（企业微信协议）
- Webhook 回调端点（URL 验证 + 消息接收）
- 语音消息下载 + ASR 转录（MiniMax / OpenAI 兼容）
- E2E 测试覆盖完整加解密往返

### 审核队列
- 提交 → 认领 → 通过/驳回 → 发送 完整工作流
- 紧急/标准双优先级（5 分钟 / 30 分钟 SLA）
- Redis 持久化 + 内存自动降级

### 数据库
- SQLite（开发） / PostgreSQL（生产）
- 7 张表：`tenants` `customers` `conversations` `audit_logs` `documents` `assets` `tax_deadlines`
- Alembic 迁移管理
- 每租户数据隔离 + 审计日志

### PDF 解析
- pdfplumber 文本提取 + 规则解析器（置信度评分）
- AI 结构化回退（规则置信度 < 70% 时调用 LLM）
- 银行对账单自动识别：机构、余额、币种、日期

### 安全
- JWT 认证 + 开发 PIN（MVP）
- AES-256-GCM 信封加密 + 字段级加密
- 租户级数据隔离 + 审计日志
- 每对话成本追踪 + 预算上限

### 前端
- Next.js 14 App Router · iPad 优先响应式
- 8 个页面：登录 / AI 对话 / 资产总览 / AI 报告 / 文档保险箱 / 审核队列 / 企业微信接入 / Agent 切换
- 4 款主题配色（鎏金 / 午夜蓝 / 翡翠绿 / 暖琥珀）
- WCAG 2.1 AA 无障碍（跳过链接、焦点环、`prefers-reduced-motion`、屏幕阅读器支持）
- 胶片颗粒纹理（SVG noise filter，可选）
- 流式 SSE 对话 + 工具调用实时展示

---

## 快速启动

### 环境要求
- Python 3.12+
- Node.js 18+
- uv（Python 包管理器）

### 1. 克隆项目
```bash
git clone https://github.com/EricHong123/butler-engine.git
cd butler-engine
```

### 2. 启动后端
```bash
cd backend
uv venv
uv sync
cp .env.example .env
# 编辑 .env，填入 LLM API Key
uvicorn butler.main:app --reload --port 8000
```

### 3. 初始化数据库
```bash
alembic upgrade head
python infra/scripts/seed_demo.py
```

### 4. 启动前端
```bash
cd frontend
npm install
npm run dev -- -p 3000
```

### 5. 打开浏览器
```
http://localhost:3000
```
登录 PIN：`888888`（张伟）/ `123456`（管理员）

---

## LLM 供应商配置

在 `backend/.env` 中设置 `BUTLER_PROVIDER` 即可切换模型：

| Provider | 模型 | 说明 |
|----------|------|------|
| `deepseek` | `deepseek-chat` | 中文流畅，性价比最高 |
| `qwen` | `qwen-plus` | 阿里通义千问 |
| `kimi` | `moonshot-v1-32k` | 128K 超长上下文 |
| `zhipu` | `glm-4-plus` | GLM-4 多模态 |
| `doubao` | `doubao-pro-256k` | 字节豆包，256K 上下文 |
| `minimax` | `abab6.5s-chat` | 语音合成强 |
| `baichuan` | `Baichuan4` | 百川智能 |
| `hunyuan` | `hunyuan-pro` | 腾讯混元 |
| `stepfun` | `step-2-16k` | 阶跃星辰 |
| `sensenova` | `SenseChat-5` | 商汤日日新 |
| `claude` | `claude-sonnet-4-6` | 最强推理+工具调用 |
| `openai` | `gpt-4o` | 综合最强 |
| `custom` | 自定义 | 任意 OpenAI 兼容端点 |

```bash
# 示例：使用 DeepSeek
BUTLER_PROVIDER=deepseek
BUTLER_CHAT_MODEL=deepseek-chat
DEEPSEEK_API_KEY=sk-xxxxxxxx
```

---

## API 端点

### 前端 API
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 当前 LLM 配置 |
| GET | `/api/agents` | 可用 Agent 列表 |
| GET | `/api/dashboard` | 资产总览数据 |
| GET | `/api/reports` | AI 报告列表 |
| GET | `/api/documents` | 文档保险库搜索 |
| POST | `/api/documents/upload` | 上传 PDF 文档 |
| POST | `/api/chat` | 流式对话（SSE） |
| POST | `/api/auth/login` | JWT 登录 |
| GET | `/api/auth/me` | 当前用户信息 |
| GET | `/api/costs` | 成本追踪汇总 |

### 企业微信
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/wechat/callback` | URL 验证（echostr） |
| POST | `/wechat/callback` | 消息回调（加解密） |

### 审核队列
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/review/tickets` | 工单列表 |
| GET | `/review/tickets/{id}` | 工单详情 |
| POST | `/review/tickets/{id}/claim` | 认领 |
| POST | `/review/tickets/{id}/approve` | 通过并发送 |
| POST | `/review/tickets/{id}/reject` | 驳回重写 |
| GET | `/review/stats` | 队列统计 |

### 企业微信接入
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/wechat-setup/status` | 配置状态 |
| POST | `/api/wechat-setup/save` | 保存配置 |
| POST | `/api/wechat-setup/test` | 测试连接 |
| GET | `/api/wechat-setup/callback-url` | 生成回调 URL |

---

## Docker 部署

```bash
docker-compose -f infra/docker-compose.prod.yml up -d
```

包含：FastAPI + Next.js + PostgreSQL 16 + Redis 7 + Nginx

---

## 项目结构

```
butler-engine/
├── backend/                          # Python FastAPI 后端
│   ├── alembic/                      # DB 迁移
│   ├── infra/scripts/                # 种子数据脚本
│   └── src/butler/
│       ├── engine/                   # Agent 运行时核心
│       │   ├── agent_runner.py       # 会话引擎（port of QueryEngine.ts）
│       │   ├── agent_loop.py         # 核心循环（port of query.ts）
│       │   ├── agent_definitions.py  # 7 个 Agent 定义 + system prompt
│       │   ├── base_tool.py          # 抽象 Tool 基类（port of Tool.ts）
│       │   ├── compact.py            # 上下文自动压缩
│       │   └── context_builder.py    # System prompt 组装
│       ├── tools/                    # 6 个专属工具
│       ├── memory/                   # 文件系统记忆（port of memdir.ts）
│       ├── wechat/                   # 企业微信集成
│       ├── review/                   # 人工审核队列
│       ├── api/                      # REST API 路由
│       ├── models/                   # SQLAlchemy ORM
│       ├── services/                 # LLM / DB / Redis / Speech
│       └── tenants/                  # 多租户隔离 + 加密
├── frontend/                         # Next.js 14 前端
│   ├── public/                       # 静态资源 + 组件 CSS
│   └── src/app/
│       ├── (dashboard)/              # 仪表盘页面组
│       │   ├── chat/                 # AI 对话页
│       │   ├── dashboard/            # 资产总览
│       │   ├── reports/              # AI 报告
│       │   ├── documents/            # 文档保险箱
│       │   ├── review/               # 审核队列
│       │   └── wechat-setup/         # 企业微信接入
│       ├── globals.css               # Tailwind + 4 款主题 CSS 变量
│       └── layout.tsx                # 根布局（跳过链接 + 颗粒滤镜）
└── infra/                            # Docker Compose + Nginx
    └── docker-compose.prod.yml
```

---

## 测试

```bash
cd backend
python -m pytest src/butler/tests/ -v
```

78 个测试全部通过：

| 测试文件 | 覆盖内容 |
|----------|---------|
| `test_agent_loop.py` | Agent 循环、工具调用、max turns |
| `test_tools.py` | 6 个工具独立测试 + 注册表 |
| `test_wechat.py` | 加密/解密、消息解析、回复构建 |
| `test_wechat_e2e.py` | 企业微信完整链路 E2E |
| `test_memory_and_profile.py` | 记忆系统、租户档案 |
| `test_review_and_safety.py` | 审核队列、加密、预算 |
| `test_speech.py` | ASR 语音转录 |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | Python 3.12 · FastAPI · Uvicorn |
| **AI/LLM** | Anthropic SDK · OpenAI SDK · 13 家供应商预设 |
| **数据库** | SQLAlchemy 2.0 · Alembic · SQLite / PostgreSQL |
| **缓存/队列** | Redis · 审核队列 |
| **加密** | PyCryptodome · AES-256-GCM · 企业微信 AES-CBC |
| **PDF** | pdfplumber |
| **前端** | Next.js 14 · React 18 · Tailwind CSS 3 |
| **部署** | Docker · Nginx |

## License

MIT
