import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ROUTES = {"ba": {"need_info", "ready"}, "tester": {"pass", "fail"}, "review": {"pass", "fail"}}
LEGACY = {
    "TEST_PASSED": "pass",
    "TEST_FAILED": "fail",
    "NEEDS_CLARIFICATION": "need_info",
    "STR_READY": "ready",
}
MARKER = re.compile(r"^@@ROUTE:\s*(\w+)[ \t]*$|\[STATUS:(\w+)\]", re.MULTILINE)


def parse_route(text: str, routing: str) -> tuple[str, str | None]:
    matches = list(MARKER.finditer(text))
    route = None
    if matches:
        last = matches[-1]
        route = last.group(1) or LEGACY.get(last.group(2))
    return MARKER.sub("", text).strip(), route if route in ROUTES.get(routing, set()) else None


def routing_instruction(routing: str) -> str:
    values = ROUTES.get(routing)
    if not values:
        return ""
    explanation = (
        "need_info nếu cần hỏi người dùng (ghi câu hỏi phía trên); ready nếu STR đã đủ."
        if routing == "ba"
        else "pass nếu đạt; fail nếu chưa đạt (ghi lý do phía trên)."
    )
    return "\n" + explanation + " Kết thúc bằng đúng một dòng @@ROUTE: " + "|".join(sorted(values))


class ReleasePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    approve: bool
    files: list[str] = Field(default_factory=list, max_length=1000)
    commit_message: str = Field(default="", max_length=1000)
    concerns: list[str] = Field(default_factory=list)


def parse_release(text: str) -> ReleasePlan:
    matches = re.findall(r"^@@RELEASE\s*\n(.*?)^@@END\s*$", text, re.MULTILINE | re.DOTALL)
    if not matches:
        raise ValueError("Leader phải trả khối @@RELEASE ... @@END")
    value: Any = json.loads(matches[-1])
    return ReleasePlan.model_validate(value)
