import asyncio

import httpx
import pytest

from app.acp.api_session import ApiAgentSession
from app.acp.pool import ACPProcessPool
from app.acp.types import AgentRuntimeConfig
from app.acp.url_policy import URLPolicy
from app.core.events import EventBus
from tests.fakes.fake_openai import app


@pytest.fixture
def config():
    return AgentRuntimeConfig(
        agent_id="api",
        handle="@custom",
        runtime="openai-api",
        model="test-model",
        base_url="http://localhost/v1",
        api_key="secret",
    )


def factory(cfg, workspace):
    return ApiAgentSession(
        cfg, workspace, policy=URLPolicy({"localhost"}, {"localhost"}), transport=httpx.ASGITransport(app=app)
    )


async def test_restart_api_agent(config, tmp_path):
    events = EventBus()
    pool = ACPProcessPool(factory=factory, event_bus=events)
    try:
        session = await pool.get_or_start(config, tmp_path, "ticket")
        assert session is await pool.get_or_start(config, tmp_path, "ticket")
        assert [event async for event in session.prompt("Go")][-1].event_type == "completed"
        async with events.subscribe("tickets/ticket") as queue, events.subscribe("users") as users:
            await pool.restart_agent("api", 2)
            assert (await queue.get())["config_version"] == 2
            assert (await users.get())["event_type"] == "agent_restarted"
        assert not session.history
        config.config_version = 2
        replacement = await pool.get_or_start(config, tmp_path, "ticket")
        assert replacement is not session and not replacement.history
        await pool.close_ticket("ticket")
        assert not pool.sessions
    finally:
        await pool.close_all()


async def test_version_change_and_capacity(config, tmp_path):
    pool = ACPProcessPool(factory=factory, max_api=1)
    try:
        first = await pool.get_or_start(config, tmp_path, "one")
        config.config_version = 2
        updated = await pool.get_or_start(config, tmp_path, "one")
        assert updated is not first and not first.alive
        waiting = asyncio.create_task(pool.get_or_start(config, tmp_path, "two"))
        await asyncio.sleep(0)
        assert not waiting.done()
        await pool.close_ticket("one")
        assert (await asyncio.wait_for(waiting, 2)).alive
    finally:
        await pool.close_all()


async def test_close_all_wakes_waiters(config, tmp_path):
    pool = ACPProcessPool(factory=factory, max_api=1)
    await pool.get_or_start(config, tmp_path, "one")
    waiting = asyncio.create_task(pool.get_or_start(config, tmp_path, "two"))
    await asyncio.sleep(0)
    await pool.close_all()
    with pytest.raises(RuntimeError, match="closed"):
        await waiting


async def test_idle_reaper(config, tmp_path):
    pool = ACPProcessPool(factory=factory, idle_timeout=0.05)
    try:
        session = await pool.get_or_start(config, tmp_path, "ticket")
        closed = asyncio.Event()
        original_close = session.close

        async def observed_close():
            await original_close()
            closed.set()

        session.close = observed_close
        await asyncio.wait_for(closed.wait(), 2)
        assert not session.alive and not pool.sessions
    finally:
        await pool.close_all()


async def test_restart_interrupts_inflight(config, tmp_path):
    config.model = "timeout"
    pool = ACPProcessPool(factory=factory)
    try:
        session = await pool.get_or_start(config, tmp_path, "ticket")
        stream = session.prompt("Go")
        await anext(stream)
        await pool.restart_agent(config.agent_id, 2)
        remaining = [event async for event in stream]
        assert remaining[-1].metadata["turn_interrupted"]
        assert session.turn_interrupted and not session.alive and not session.history
    finally:
        await pool.close_all()


async def test_slow_start_does_not_block_other_tickets_or_shutdown(config, tmp_path):
    entered = asyncio.Event()

    def slow_factory(cfg, workspace):
        session = factory(cfg, workspace)
        if cfg.agent_id == "slow":

            async def start():
                entered.set()
                await asyncio.Event().wait()

            session.start = start
        return session

    pool = ACPProcessPool(factory=slow_factory, max_api=2)
    slow_cfg = config.model_copy(update={"agent_id": "slow"})
    waiting = asyncio.create_task(pool.get_or_start(slow_cfg, tmp_path, "one"))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        fast = await asyncio.wait_for(pool.get_or_start(config, tmp_path, "two"), 2)
        assert fast.alive
        await asyncio.wait_for(pool.close_all(), 2)
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert not pool.sessions
    finally:
        await pool.close_all()
        await asyncio.gather(waiting, return_exceptions=True)


async def test_restart_interrupts_native_turn(make_session, handshake, cfg, tmp_path):
    ready = {
        "notify": "session/update",
        "params": {
            "sessionId": "session-1",
            "update": {"sessionUpdate": "agent_message_chunk", "content": {"text": "Ready"}},
        },
    }

    def native_factory(config, workspace):
        return make_session(
            [
                *handshake,
                {
                    "expect": "session/prompt",
                    "then": [ready],
                    "wait_for_cancel": True,
                    "reply": {"stopReason": "cancelled"},
                },
            ],
            config,
        )

    pool = ACPProcessPool(factory=native_factory)
    try:
        session = await pool.get_or_start(cfg, tmp_path, "ticket")
        stream = session.prompt("Go")
        assert (await anext(stream)).content == "Ready"
        await pool.restart_agent(cfg.agent_id, 2)
        remaining = [event async for event in stream]
        assert remaining[-1].metadata["turn_interrupted"]
        assert not session.alive and session.process.returncode is not None
    finally:
        await pool.close_all()
