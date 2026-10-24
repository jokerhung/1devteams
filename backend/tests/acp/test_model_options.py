import pytest

from app.acp.config_options import describe


@pytest.mark.parametrize("legacy", [False, True])
async def test_model_change_refreshes_reasoning_options(make_session, cfg, legacy):
    cfg.model = "new-model[deep]" if legacy else "new-model"
    cfg.reasoning_effort = None if legacy else "deep"
    model = {
        "id": "model-choice",
        "category": "model",
        "type": "select",
        "options": [{"group": "all", "options": [{"value": "new-model", "name": "New"}]}],
    }
    effort = {
        "id": "budget",
        "category": "thought_level",
        "type": "select",
        "options": [{"value": "deep", "name": "Deep"}],
        "currentValue": "deep",
    }
    session = make_session(
        [
            {"expect": "initialize", "reply": {"protocolVersion": 1}},
            {"expect": "session/new", "reply": {"sessionId": "s", "configOptions": [model]}},
            {
                "expect": "session/set_config_option",
                "assert_params": {"configId": "model-choice", "value": "new-model"},
                "reply": {"configOptions": [model, effort]},
            },
            {
                "expect": "session/set_config_option",
                "assert_params": {"configId": "budget", "value": "deep"},
                "reply": {"configOptions": [model, effort]},
            },
        ],
        cfg,
    )
    try:
        await session.start()
        data = session.model_options()
        assert data["models"][0]["id"] == "new-model"
        assert data["reasoning_levels"] == [{"id": "deep", "label": "Deep"}]
    finally:
        await session.close()


@pytest.mark.parametrize("effort", [None, "high"])
async def test_legacy_combined_model_reasoning(make_session, cfg, effort):
    cfg.model, cfg.reasoning_effort = "legacy", effort
    session = make_session(
        [
            {"expect": "initialize", "reply": {"protocolVersion": 1}},
            {
                "expect": "session/new",
                "reply": {
                    "sessionId": "s",
                    "models": {
                        "currentModelId": "legacy[low]",
                        "availableModels": [
                            {"modelId": "legacy[low]", "name": "Legacy (low)"},
                            {"modelId": "legacy[high]", "name": "Legacy (high)"},
                        ],
                    },
                },
            },
            {"expect": "session/set_model", "assert_params": {"modelId": f"legacy[{effort or 'low'}]"}},
        ],
        cfg,
    )
    try:
        await session.start()
        data = session.model_options()
        assert [model["id"] for model in data["models"]] == ["legacy"]
        assert [level["id"] for level in data["models"][0]["reasoning_levels"]] == ["low", "high"]
    finally:
        await session.close()


async def test_unadvertised_reasoning_is_rejected(make_session, handshake, cfg):
    cfg.reasoning_effort = "invented"
    session = make_session(handshake, cfg)
    with pytest.raises(ValueError, match="reasoning"):
        await session.start()
    assert not session.alive


def test_flatten_grouped_model_and_effort_options():
    data = describe(
        [
            {"id": "model", "options": [{"group": "a", "options": [{"value": "model", "name": "Model"}]}]},
            {"id": "effort", "options": [{"group": "b", "options": [{"value": "high", "name": "High"}]}]},
        ],
        [],
    )
    assert data["models"][0]["label"] == "Model"
    assert data["reasoning_levels"] == [{"id": "high", "label": "High"}]
