"""
Streaming chat API. SSE-based endpoint for the conversational agent.

POST /api/chat — sends message, returns SSE stream of agent events
GET  /api/conversations/{id} — get conversation history
"""

from __future__ import annotations

import json
import uuid
import asyncio

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from butler.api.authorization import can_use_agent, is_sensitive_agent
from butler.api.deps import get_agent_tools, get_full_registry
from butler.api.schemas import ChatRequest
from butler.engine.agent_definitions import DEFAULT_AGENT, AGENT_ICONS, get_agent, list_agents
from butler.engine.agent_runner import AgentRunner, AgentRunnerConfig
from butler.engine.context_builder import build_system_prompt
from butler.memory.memory_manager import MemoryManager
from butler.config import settings
from butler.services.llm.client import get_llm_client
import time as _time

router = APIRouter(prefix="/api", tags=["conversation"])

# Per-agent runners: key = (tenant_id, agent_type)
_runners: dict[str, AgentRunner] = {}


def _runner_key(tenant_id: str, agent_type: str) -> str:
    return f"{tenant_id}:{agent_type}"


@router.get("/agents")
async def get_agents():
    """List all available agents."""
    return {"agents": list_agents(), "default": DEFAULT_AGENT}


def _extract_role_from_token(authorization: str | None) -> str:
    """Extract user role from JWT Bearer token. Returns 'principal' if no token."""
    if not authorization or not authorization.startswith("Bearer "):
        return "principal"
    try:
        from butler.api.router_auth import verify_token
        payload = verify_token(authorization[7:])
        return payload.get("role", "principal")
    except Exception:
        return "principal"


@router.post("/chat")
async def chat(request: ChatRequest, authorization: str | None = Header(None, alias="Authorization")):
    """
    Streaming chat endpoint. Returns SSE (Server-Sent Events) stream.

    Accepts agent_type to switch between specialized agents.
    Each agent has its own system prompt, tool set, and conversation context.
    """
    tenant_id = request.tenant_id
    agent_type = request.agent_type or DEFAULT_AGENT

    # Authorization: extract role from JWT and check against agent allowlist
    user_role = _extract_role_from_token(authorization)
    if not can_use_agent(user_role, agent_type):
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{agent_type}' is not available for role '{user_role}'",
        )

    # Sensitive agent gate: only principal and admin can use wealth/tax agents
    if is_sensitive_agent(agent_type) and user_role not in ("principal", "admin"):
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{agent_type}' requires principal or admin role, not '{user_role}'",
        )

    agent = get_agent(agent_type)
    tools = get_agent_tools(agent_type)

    # Load profile
    profile_md = None
    profile_path = settings.data_root / tenant_id / "profile" / "CLAUDE.md"
    if profile_path.exists():
        profile_md = profile_path.read_text(encoding="utf-8")

    # Load memory
    memory_mgr = MemoryManager(tenant_id, settings.data_root)
    memory_idx = await memory_mgr.load_index()

    # Build system prompt using agent-specific prompt
    system_prompt = await build_system_prompt(
        tenant_id=tenant_id,
        profile_markdown=profile_md,
        memory_index=memory_idx,
        custom_override=agent.system_prompt,
    )

    # Get or create agent-scoped runner
    key = _runner_key(tenant_id, agent_type)
    conv_id = request.conversation_id or key

    if key not in _runners:
        config = AgentRunnerConfig(
            tenant_id=tenant_id,
            tools=tools,
            profile_markdown=profile_md,
            memory_index=memory_idx,
            custom_system_prompt=agent.system_prompt,
        )
        llm = None
        if settings.resolved_api_key:
            try:
                llm = get_llm_client()
            except Exception:
                pass
        runner = AgentRunner(config, llm=llm)
        _runners[key] = runner
    else:
        runner = _runners[key]

    # Check if we have a working LLM
    if runner._llm is None:
        return StreamingResponse(
            _mock_chat_stream(request.message, tools, conv_id, agent_type, profile_md, memory_idx, tenant_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    start_time = _time.time()

    async def event_stream():
        try:
            async for event in runner.submit_message(request.message):
                event_data = {
                    "type": event.type,
                    "data": event.data if isinstance(event.data, (str, type(None))) else event.data,
                    "conversation_id": conv_id,
                }
                yield f"data: {json.dumps(event_data, ensure_ascii=False, default=str)}\n\n"

                # Check for abort
                if event.type == "done":
                    break

        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'done', 'data': 'Cancelled', 'conversation_id': conv_id})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc), 'conversation_id': conv_id})}\n\n"
        finally:
            # Audit log
            elapsed = _time.time() - start_time
            try:
                from butler.repositories.conversation_repo import AuditLogRepo
                from butler.services.database import get_sessionmaker
                async with get_sessionmaker()() as s:
                    repo = AuditLogRepo(s)
                    await repo.log(
                        tenant_id=tenant_id,
                        action="chat_message",
                        actor="customer",
                        details=f"agent={agent_type} elapsed={elapsed:.1f}s msg={request.message[:100]}",
                    )
                    await s.commit()
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/costs")
async def get_cost_summary():
    """Get cost tracking summary."""
    try:
        from butler.services.database import get_sessionmaker
        from sqlalchemy import text
        async with get_sessionmaker()() as s:
            # Sum costs from conversations
            result = await s.execute(text(
                "SELECT COUNT(*) as total_convs, COALESCE(SUM(total_cost_usd),0) as total_cost, "
                "COALESCE(SUM(total_tokens_used),0) as total_tokens FROM conversations"
            ))
            row = result.fetchone()
            return {
                "total_conversations": row[0],
                "total_cost_usd": round(row[1], 4),
                "total_tokens": row[2],
                "budget_limit_usd": settings.max_budget_usd,
            }
    except Exception:
        return {"total_conversations": 0, "total_cost_usd": 0, "total_tokens": 0, "note": "DB unavailable"}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Get message history for a conversation."""
    runner = _runners.get(conv_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "conversation_id": conv_id,
        "messages": runner.messages,
        "session_id": runner.get_session_id(),
    }


@router.get("/config")
async def get_chat_config():
    """Return current LLM configuration (safe for frontend display)."""
    return {
        "provider": settings.provider or "custom",
        "model": settings.resolved_model,
        "base_url": settings.resolved_base_url,
        "provider_type": settings.resolved_provider_type,
        "has_api_key": bool(settings.resolved_api_key),
    }


@router.post("/conversations/reset")
async def reset_conversation(tenant_id: str = "demo-001", agent_type: str = "butler"):
    """Reset a conversation for a specific agent (clear history)."""
    key = _runner_key(tenant_id, agent_type)
    if key in _runners:
        del _runners[key]
    return {"status": "reset", "tenant_id": tenant_id, "agent_type": agent_type}


# ── Mock Chat (no API keys) ──

import re as _re

async def _mock_chat_stream(
    message: str,
    tools,
    conv_id: str,
    agent_type: str,
    profile_md: str | None,
    memory_idx: str | None,
    tenant_id: str = "demo-001",
):
    """Fallback chat that uses real tools with mock data. No LLM API call needed."""
    msg_lower = message.lower()
    tool = None
    tool_input = {}

    # Match intent to tool
    if any(w in msg_lower for w in ['资产', '账户', '余额', 'portfolio', 'wealth', 'asset', '持有']):
        tool = tools.find('query_assets')
        tool_input = {'query': 'all'}
    elif any(w in msg_lower for w in ['税', 'tax', '申报', '截止', 'deadline']):
        tool = tools.find('check_tax_calendar')
        tool_input = {}
    elif any(w in msg_lower for w in ['文档', '合同', '保单', '文件', 'document', 'contract']):
        tool = tools.find('search_docs')
        tool_input = {'query': message}
    elif any(w in msg_lower for w in ['日程', '预约', '日历', '提醒', 'appointment', 'schedule']):
        tool = tools.find('schedule_event')
        tool_input = {'action': 'list'}
    elif any(w in msg_lower for w in ['报告', '月报', '季报', 'report']):
        tool = tools.find('generate_report')
        tool_input = {'report_type': 'asset_monthly', 'period': '2026-04'}
    elif any(w in msg_lower for w in ['人工', '转接', '律师', '医生', '顾问']):
        tool = tools.find('escalate_to_human')
        tool_input = {'reason': 'customer_request', 'priority': 'standard'}

    # Yield tool call + result
    tool_id = str(uuid.uuid4())
    tool_name = tool.name if tool else 'no_tool'

    if tool:
        import json as _json
        yield f"data: {_json.dumps({'type': 'tool_call', 'data': {'id': tool_id, 'name': tool_name, 'input': tool_input}, 'conversation_id': conv_id}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.3)

        from butler.engine.agent_loop import ToolUseContext as _ToolUseContext
        result = await tool.call(tool_input, _ToolUseContext(tenant_id, []))
        result_text = _json.dumps(result.data, ensure_ascii=False, default=str)
        yield f"data: {_json.dumps({'type': 'tool_result', 'data': {'tool_use_id': tool_id, 'result': result_text}, 'conversation_id': conv_id}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.2)

    # Yield text response
    response = _generate_mock_response(message, tool_name, tool_input)
    for i in range(0, len(response), 3):
        chunk = response[i:i+3]
        yield f"data: {_json.dumps({'type': 'text_delta', 'data': chunk, 'conversation_id': conv_id}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.03)

    yield f"data: {_json.dumps({'type': 'done', 'data': None, 'conversation_id': conv_id}, ensure_ascii=False)}\n\n"


def _generate_mock_response(user_msg: str, tool_name: str, tool_input: dict) -> str:
    """Generate realistic Chinese response based on tool used."""
    responses = {
        'query_assets': '根据查询，您当前总资产约¥1.72亿，其中：\n\n📊 银行存款 ¥975万\n📈 证券投资 ¥2,500万\n🏛️  信托资产 ¥8,000万\n🛡️  保险 ¥580万\n🏠 不动产 ¥5,700万\n\n本月环比增长1.2%。需要重点关注：CMB活期余额偏高（¥850万），建议将超过¥500万部分转投短期理财。',
        'check_tax_calendar': '以下是近期税务节点：\n\n🔴 紧急：香港物业税申报截止 5月31日\n🔴 紧急：CRS信息申报截止 5月31日\n🟡 关注：个人所得税汇算清缴 6月30日\n🟡 关注：香港利得税申报 8月15日\n\n共6项待办，其中2项需本月内完成。',
        'search_docs': '文档保险库中有7个匹配文件，包括：银行对账单2份、信托契约1份、保险合同1份、房产税单1份、体检报告1份、录取通知书1份。需要查看哪个文件的具体内容？',
        'schedule_event': '您近期日程：\n\n📅 5/15 14:00 季度资产回顾会议（与陈律师）\n📅 5/20 10:00 洪悦钢琴比赛（上海音乐学院）\n📅 5/31 23:59 香港物业税申报截止\n📅 6/1 09:00 友邦保险年缴保费\n📅 6/7 08:00 洪明SAT考试\n\n需要预约新的事项吗？',
        'generate_report': '已为您生成2026年4月资产月报。报告包含：资产分布概览、流动性分析、月度变动明细、下月重点关注事项。您可以在「AI报告」页面查看和下载完整报告。',
        'escalate_to_human': '已为您创建审核工单。根据我们的流程，涉及法律、医疗或重大财务决策的请求需要专业顾问审核后回复。预计30分钟内会有专人通过微信与您联系。',
    }

    base = responses.get(tool_name, '')
    if base:
        return base
    return f'您好，我是您的私人AI管家。关于「{user_msg[:30]}」，我可以帮您：\n\n• 查询资产和账户信息\n• 检查税务截止日期\n• 搜索您的文档保险库\n• 查看和管理日程\n• 生成各类报告\n\n请告诉我您需要什么帮助？'

