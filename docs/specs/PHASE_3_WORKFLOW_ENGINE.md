# PHASE 3 — Workflow Engine (LangGraph động), Human Gates, GitService & Realtime

## 1. Mục tiêu
1. Biên dịch `workflow.graph` (JSON React Flow — schema Phase 2 §5) thành `StateGraph` LangGraph chạy được, hỗ trợ vòng lặp, rẽ nhánh, `interrupt()` chờ người dùng.
2. Chạy ticket ở background, stream mọi sự kiện agent (Phase 1) → lưu `ticket_messages` → đẩy WebSocket.
3. Human-in-the-loop: BA hỏi lại (`human_input`), user xác nhận/từ chối (`human_confirm`).
4. `git_release`: Leader (LLM) review diff + đề xuất commit; **backend `GitService` thực thi** add/commit/push một cách tất định.

## 2. Cấu trúc file
```text
backend/app/
├── core/events.py        # EventBus (in-process pub/sub theo ticket_id)
├── engine/
│   ├── state.py          # WorkflowState
│   ├── prompts.py        # DEFAULT_SYSTEM_PROMPTS + builder prompt theo node
│   ├── markers.py        # parse @@ROUTE / @@RELEASE
│   ├── nodes.py          # factory cho từng loại node
│   ├── compiler.py       # graph JSON → CompiledStateGraph
│   └── runner.py         # TicketRunner: start / resume / cancel, workspace lock
├── services/git_service.py
├── api/tickets.py        # thêm action endpoints
└── ws/ manager.py, ticket_ws.py
backend/tests/engine/ ...
```

## 3. State (`engine/state.py`)
State **tổng quát** (không gắn cứng 4 role) để custom agent chèn vào đâu cũng được:
```python
class NodeOutput(TypedDict):
    node_id: str
    agent_handle: str
    text: str                 # câu trả lời cuối (đã bỏ marker)
    route: str | None         # need_info | ready | pass | fail | ...
    modified_files: list[str]
    at: str                   # ISO time

class WorkflowState(TypedDict):
    ticket_id: str
    project_id: str
    workspace_path: str
    title: str
    description: str
    outputs: Annotated[list[NodeOutput], operator.add]      # lịch sử output theo thứ tự
    user_inputs: Annotated[list[dict], operator.add]        # {node_id, kind: answer|feedback|approve, text, user}
    last_route: dict[str, str]                              # node_id -> handle vừa chọn
    modified_files: list[str]                               # tích lũy (set → list)
    iteration: dict[str, int]                               # node_id -> số lần đã chạy
    release: dict | None                                    # {commit_hash, branch, files, message}
    error: str | None
```

## 4. Quy ước marker điều hướng (`engine/markers.py`)
Prompt builder **luôn** thêm hướng dẫn cuối prompt tùy `routing` của node:

| routing | Hướng dẫn thêm | Giá trị hợp lệ |
|---------|---------------|----------------|
| `ba` | “Kết thúc câu trả lời bằng đúng 1 dòng `@@ROUTE: need_info` nếu cần hỏi người dùng (đặt câu hỏi ngay phía trên), hoặc `@@ROUTE: ready` nếu STR đã đủ.” | `need_info`, `ready` |
| `tester` / `review` | “… `@@ROUTE: pass` nếu đạt, `@@ROUTE: fail` nếu chưa đạt (nêu rõ lý do phía trên).” | `pass`, `fail` |
| `none` | không thêm | — |

Parser: regex `^@@ROUTE:\s*(\w+)\s*$` (multiline), lấy **lần xuất hiện cuối**; xóa dòng marker khỏi text hiển thị. Chấp nhận cả dạng cũ `[STATUS:TEST_PASSED]`/`[STATUS:TEST_FAILED]`/`[STATUS:NEEDS_CLARIFICATION]`/`[STATUS:STR_READY]` (map tương ứng).
Thiếu/không hợp lệ → **gửi 1 prompt bổ sung** trong cùng session: “Chỉ trả lời đúng 1 dòng: `@@ROUTE: <a>|<b>`”. Vẫn lỗi → coi như `need_info` (BA) / `fail` (tester) + event `error` cảnh báo.

Leader dùng marker khối JSON:
```text
@@RELEASE
{"approve": true, "files": ["src/pages/Reconciliation/ExportButton.tsx"],
 "commit_message": "fix(reconciliation): async stream excel export", "concerns": []}
@@END
```

## 5. Prompt builder (`engine/prompts.py`)
`build_node_prompt(node, agent, state, is_first_turn_in_session) -> str`:
- Lượt đầu của agent trong ticket: gồm
  1. `# Ticket #{number}: {title}` + mô tả.
  2. Workspace: `{workspace_path}` (nhắc chỉ làm việc trong thư mục này).
  3. Ngữ cảnh từ các output trước (theo thứ tự, mỗi mục ≤ 4.000 ký tự, giữ mới nhất nếu vượt tổng 16.000): `## Output của @ba`, `## Output của @developer`…
  4. Trả lời của user (`user_inputs`) liên quan.
  5. `node.data.instructions` (override/bổ sung từ canvas).
  6. Hướng dẫn marker (§4).
- Lượt sau (session đã có ngữ cảnh): chỉ gửi **phần mới** kể từ lượt trước của agent đó (output mới của agent khác + feedback mới của user) + hướng dẫn marker.
- **Agent `openai-api` (text-only)**: không tự đọc được workspace nên prompt builder **bơm ngữ cảnh** thay vì chỉ nhắc đường dẫn: (a) mô tả ticket + STR/output các agent trước (như trên); (b) `git diff` của `state.modified_files` (cắt mỗi file ≤ 12.000 ký tự, tổng ≤ `API_CONTEXT_DIFF_CHARS=40.000`, ghi rõ phần bị cắt); (c) với agent có `routing: ba/review`, thêm nội dung vài file **được chỉ định** trong `node.data.context_files` (tối đa 5 file, qua `fs` handler **chỉ đọc**, có áp dụng path-guard & chặn `.env`). Nhắc rõ trong prompt: “Bạn không có công cụ; chỉ dùng thông tin được cung cấp, không giả vờ đã chạy lệnh”.
- System prompt agent truyền qua kênh system prompt của ACP (Phase 1), không lặp trong prompt.

## 6. Node factory (`engine/nodes.py`)
Mọi node nhận `RunContext` qua `config["configurable"]["ctx"]` (pool ACP, EventBus, DB session factory, GitService, ticket meta). **Không** đặt object không serialize được vào state.

### 6.1. `agent` node
```text
1. iteration[node_id] += 1; nếu > MAX_NODE_ITERATIONS (mặc định 5) → interrupt human_input
   "Luồng đã lặp quá 5 lần ở {handle}. Nhập hướng dẫn để tiếp tục hoặc huỷ ticket."
2. emit agent_turn_start {node_id, agent_handle, model}; cập nhật ticket.current_node_id, status RUNNING.
3. session = pool.get_or_start(agent_cfg, workspace, ticket_id)   # factory theo runtime: ACPSession (claude-code/codex) hoặc ApiAgentSession (openai-api)
4. async for ev in session.prompt(prompt): persist + publish (mỗi event `tool_call`/`permission`/`thought_chunk`/`plan`/`error` cũng là một **dòng log agent** hiển thị gắn vào lượt chat — UI chuẩn hoá bằng `toLogLine`, Phase 6 §5.3b; engine bổ sung các dòng hệ thống `→ session/new cwd=…`, `→ session/prompt (<runtime> · <model>)`, `✔ stopReason=end_turn` cùng `run_id`) (gộp message_chunk/thought_chunk
   theo cửa sổ 150ms trước khi publish để giảm tải WS; DB lưu bản gộp).
5. Parse marker → route; strip text.
6. emit agent_turn_end {node_id, route, modified_files}
7. return {outputs:[NodeOutput], last_route:{node_id: route}, modified_files: merged, iteration: ...}
```
**Agent bị khởi động lại giữa lượt** (`agent_restarted` / `turn_interrupted`, Phase 1 §3.6) → bỏ kết quả dở, phát dòng log `↻ lượt bị dừng do sửa cấu hình agent, chạy lại` và chạy lại node với session mới (1 lần, không tính vào số vòng lặp). Lỗi ACP (process chết, timeout) → retry 1 lần với session mới; vẫn lỗi → `error` event, ticket `FAILED`, state.error.

### 6.2. `human_input` node
```python
payload = {"kind": "human_input", "node_id": nid,
           "question": last_output_text_of_previous_agent, "prompt_hint": "@ba đang chờ bạn bổ sung thông tin..."}
emit gate_waiting(payload); set ticket WAITING_USER_INPUT
create_notification(type="INPUT", ticket, node_id, title=f"@{agent.handle} cần bạn trả lời để lập kịch bản",
                    body="Agent hỏi thêm thông tin trước khi chuyển bước tiếp theo.")   # idempotent theo gate_key
answer = interrupt(payload)       # resume value: {"text": "...", "user": {...}}
resolve_notifications(ticket, node_id, outcome="ANSWERED")
return {"user_inputs": [{"node_id": nid, "kind": "answer", "text": answer["text"], "user": answer["user"]}]}
```
> Lưu ý LangGraph: khi resume, node chạy lại **từ đầu** → emit `gate_waiting` phải idempotent (khóa theo `(ticket_id, node_id, interrupt_seq)`; không phát lại nếu đã phát).

### 6.3. `human_confirm` node
```python
payload = {"kind":"human_confirm","node_id":nid,"message":data.message,
           "modified_files": state.modified_files}
set ticket WAITING_USER_CONFIRM; emit gate_waiting(payload)
create_notification(type="CONFIRM", ticket, node_id, title="Xác nhận bản sửa lỗi để @leader commit & push",
                    body=f"Ticket #{code} đã qua kiểm thử, đang chờ bạn xác nhận.")   # idempotent theo gate_key
decision = interrupt(payload)     # {"approved": bool, "feedback": str|None, "user": {...}}
resolve_notifications(ticket, node_id, outcome="APPROVED" if decision["approved"] else "REJECTED")
route = "approved" if decision["approved"] else "rejected"
return {"last_route": {nid: route}, "user_inputs": [{"node_id":nid,"kind":"approve" if ... else "feedback", ...}]}
```

### 6.4. `condition` node
Biểu thức an toàn (không `eval`): hỗ trợ `last_route.<node_id> == "<v>"`, `len(modified_files) > 0`, `iteration.<node_id> >= N`. Parse bằng mini-parser hoặc thư viện `simpleeval` với whitelist.

### 6.5. `git_release` node
```text
1. Kiểm tra agent.permission_profile.can_git_release, nếu không → FAILED.
2. git_service.snapshot(): status --porcelain, diff --stat, diff (giới hạn 60k ký tự), current branch.
   Không có thay đổi → emit message "Không có thay đổi để commit" → route failed.
3. Prompt Leader: diff + danh sách file + ticket + output tester; yêu cầu khối @@RELEASE.
4. Parse JSON (pydantic ReleasePlan). approve=false → emit concerns → route "failed".
5. Kiểm tra plan: files ⊆ changed files; loại file nhạy cảm (.env*, *.log, *.pem, node_modules/, dist/) → nếu có thì loại + cảnh báo;
   commit_message khớp Conventional Commits `^(feat|fix|refactor|perf|test|docs|chore|build|ci|style)(\(.+\))?: .{3,}`
   (không khớp → tự sửa thành `fix: <message>`).
6. git_service.commit_and_push(files, message, remote=project.git_remote, branch=current_branch)
7. emit terminal_output cho từng lệnh (stdout/stderr), emit message tổng kết của @leader:
   "Đã push commit `8c3d91a` lên `hotfix/reconciliation` — 1 file changed..."
8. return {release: {...}, last_route: {nid: "success"}}
```

### 6.6. `start` / `end`
- `start`: emit `ticket_status RUNNING`.
- `end`: cập nhật ticket `COMPLETED` (hoặc `FAILED` nếu state.error), lưu `result`, `pool.close_ticket()`, nhả workspace lock.

## 7. GitService (`services/git_service.py`)
- Chỉ thực thi qua `asyncio.create_subprocess_exec("git", ...)` với **danh sách lệnh trắng**: `status`, `diff`, `log`, `rev-parse`, `branch --show-current`, `add -- <files>`, `commit -m <msg>`, `push <remote> <branch>`.
- Thư mục file đính kèm (`.aiteams/attachments/`) tự thêm vào `.git/info/exclude` của workspace; `git_release` loại mọi đường dẫn này khỏi danh sách commit.
- Cấm tuyệt đối: `--force`, `-f`, `reset --hard`, `clean`, `checkout --`, `rebase`, `push` không chỉ định nhánh.
- Trước push: `git rev-parse --abbrev-ref HEAD` phải khác `HEAD` (không detached). Nếu branch hiện tại ≠ `project.default_branch` → vẫn push branch hiện tại nhưng emit cảnh báo.
- Push lỗi (VD rejected non-fast-forward, auth) → giữ commit local, ticket `FAILED` kèm hướng dẫn, **không** tự pull/rebase.
- Trả `ReleaseResult {commit_hash (short+full), branch, files, insertions, deletions, push_output}`.
- Timeout mỗi lệnh 120s; log đầy đủ vào `ticket_messages` (event `terminal_output`, sender `@leader`).

## 8. Compiler (`engine/compiler.py`)
```python
def compile_workflow(graph: WorkflowGraph, agents: dict[str, AgentRuntimeConfig], checkpointer) -> CompiledStateGraph:
    validate(graph)                         # dùng lại validator Phase 2, raise nếu invalid
    sg = StateGraph(WorkflowState)
    for n in graph.nodes: sg.add_node(n.id, make_node(n, agents))
    sg.add_edge(START, start_node.id)
    for src, outs in group_edges_by_source(graph.edges):
        if len(outs) == 1 and outs[0].sourceHandle in (None, "default"):
            sg.add_edge(src, outs[0].target)
        else:
            mapping = {e.sourceHandle: e.target for e in outs}
            sg.add_conditional_edges(src, lambda s, _src=src: s["last_route"][_src], mapping)
    for end in end_nodes: sg.add_edge(end.id, END)
    return sg.compile(checkpointer=checkpointer)
```
- Checkpointer: `AsyncSqliteSaver` (dev, file `CHECKPOINT_DB`) / `AsyncPostgresSaver` (prod). `thread_id = ticket_id`.
- Cache compiled graph theo `(workflow_id, version)`.
- `recursion_limit` = 100.

## 9. TicketRunner (`engine/runner.py`)
```python
class TicketRunner:
    async def start(ticket_id, user) -> None        # OPEN → RUNNING; tạo task nền
    async def reply(ticket_id, text, user) -> None  # chỉ khi WAITING_USER_INPUT → Command(resume={"text":..,"user":..})
    async def confirm(ticket_id, approved, feedback, user) -> None   # chỉ khi WAITING_USER_CONFIRM
    async def cancel(ticket_id, user) -> None       # session/cancel mọi ACP của ticket, task.cancel(), CANCELLED
```
- **Graph chạy = snapshot của workflow mà ticket thuộc về**: `start()` nạp `workflow_versions(ticket.workflow_id, ticket.workflow_version).graph` → compile (cache theo `(workflow_id, version)`). Không bao giờ đọc graph nháp. Mỗi project có thể có nhiều workflow, các ticket thuộc workflow khác nhau chạy graph khác nhau.
- `start()` được gọi tự động ngay sau khi tạo ticket (`auto_start=true`, Phase 2 §6.6) để cửa sổ chat mở ra là thấy `@ba` bắt đầu làm việc.
- Chạy bằng `graph.ainvoke(input_or_Command, config={"configurable": {"thread_id": tid, "ctx": ctx}})` trong `asyncio.create_task`; giữ registry `ticket_id → Task`.
- Sau mỗi lần `ainvoke` dừng do interrupt: đọc `graph.aget_state()` → xác định gate đang chờ → đảm bảo status ticket đúng.
- **Workspace lock**: `asyncio.Lock` theo `workspace_path` (chuẩn hóa) — áp dụng chung cho **mọi workflow** của project (các workflow dùng chung một thư mục mã nguồn). Ticket khác cùng workspace bấm Start → không lỗi mà **xếp hàng**: ticket ở trạng thái `OPEN` kèm event SYSTEM “Đang chờ ticket #BUG-104 (workflow Fix Bug) giải phóng workspace…”, tự chạy khi lock nhả (hàng đợi FIFO theo project). Lock giữ suốt RUNNING; nhả khi WAITING_* ? → **Không nhả** khi WAITING_USER_CONFIRM (code chưa commit), có nhả khi WAITING_USER_INPUT ở BA trước khi developer chạy lần nào (chưa sửa file). Ghi rõ trong code.
- Khởi động lại server: ticket `RUNNING` → chuyển `FAILED` với lý do “server restart” + cho phép `POST /tickets/{id}/retry` (resume từ checkpoint cuối); ticket `WAITING_*` vẫn resume bình thường nhờ checkpointer.
- Phân quyền: chỉ user là member (MAINTAINER/REPORTER) của project mới start/reply; chỉ MAINTAINER (hoặc reporter nếu cấu hình) mới `confirm`.

## 10. EventBus & persistence
- `EventBus.publish(ticket_id, AgentEvent)`: ghi DB (gán `seq` tăng dần bằng counter theo ticket, khởi tạo từ max(seq)) rồi fan-out tới mọi subscriber `asyncio.Queue` (maxsize 1000; đầy → ngắt client chậm).
- Interface tách biệt để sau thay bằng Redis Pub/Sub khi chạy nhiều worker.

## 11. API & WebSocket

### 11.1. REST actions (`api/tickets.py`)
| Method | Path | Body |
|--------|------|------|
| POST | `/tickets/{id}/start` | — |
| POST | `/tickets/{id}/reply` | `{text}` |
| POST | `/tickets/{id}/confirm` | `{approved: bool, feedback?: str}` |
| POST | `/tickets/{id}/cancel` | — |
| POST | `/tickets/{id}/retry` | — |
| POST | `/tickets/{id}/messages` | `{text, attachment_ids?: []}` — chat tự do; xử lý theo §11.3. Client đã tự thêm `@<agent mặc định>` vào `text` nếu người dùng chưa gõ mention (Phase 6 §5.7) — backend chỉ parse mention trong text. Cho phép `text` rỗng nếu có `attachment_ids` |
| GET | `/tickets/{id}/state` | `{status, current_node_id, waiting: {kind, node_id, payload} | null, node_statuses: {node_id: idle|running|done|waiting|failed}}` |

### 11.2. WebSocket `WS /ws/tickets/{ticket_id}?token=<jwt>&after_seq=<n>`
- Thêm kênh nhẹ `WS /ws/projects/{project_id}` chỉ phát `ticket_created`, `ticket_status` (kèm `workflow_id`) để sidebar cây Project → Workflow → Ticket cập nhật realtime; và kênh `WS /ws/users/me` phát `notification_created`, `notification_resolved`, `agent_restarted` (badge “Thông báo” ở sidebar, trạng thái “Đang khởi động lại…” ở trang Agents).
- Khi connect: gửi `{"type":"snapshot","state":<GET state>}` rồi replay các message `seq > after_seq` (`{"type":"event","data":AgentEvent}`), sau đó stream realtime.
- Server → client: `event`, `snapshot`, `ping` (mỗi 25s).
- Client → server: `{"type":"pong"}`; các action **cũng chấp nhận** qua WS (`{"type":"action","action":"reply|confirm|start|cancel", ...}`) và gọi chung TicketRunner — để giữ tương thích với thiết kế trong PDF.

### 11.3. Chat tự do & lệnh gõ tay (theo mockup)
Text user gửi vào `/messages` (kèm file đính kèm nếu có — backend gắn `message_id` cho các `attachments`, ghi file vào thư mục đính kèm của ticket và thêm mục `## File đính kèm` (đường dẫn + mô tả; ảnh dạng image block nếu runtime hỗ trợ) vào prompt lượt kế tiếp của agent được mention):
- Ticket `WAITING_USER_INPUT` → coi là `reply`.
- Ticket `WAITING_USER_CONFIRM` và text chứa `@leader` + một trong `CONFIRM|DONE|OK|ĐÃ FIX|XÁC NHẬN` (không phân biệt hoa thường) → `confirm(approved=true)`; chứa `@developer` + nội dung khác → `confirm(approved=false, feedback=text)`.
- Ticket `OPEN` → lưu như mô tả bổ sung; nếu chứa `@ba` → `start`.
- Trường hợp khác → chỉ lưu message `USER` (agent đọc ở lượt kế tiếp qua prompt builder).

## 12. Test (`tests/engine/`) — dùng fake ACP agent từ Phase 1
| Test | Kịch bản |
|------|---------|
| `test_compiler_default_template` | compile template mặc định thành công; graph invalid → raise |
| `test_ba_clarification_loop` | fake BA lần 1 `@@ROUTE: need_info` → state WAITING_USER_INPUT → reply → BA lần 2 `ready` → developer chạy |
| `test_tester_fail_loops_back` | tester `fail` → developer chạy lại (iteration=2) → tester `pass` → WAITING_USER_CONFIRM |
| `test_confirm_reject` | confirm(approved=false, feedback) → developer nhận feedback trong prompt |
| `test_release_success` | repo git tạm + remote bare tạm → confirm → leader @@RELEASE → commit tồn tại ở remote, ticket COMPLETED, `result.commit_hash` đúng |
| `test_release_filters_sensitive` | plan chứa `.env` → bị loại, cảnh báo |
| `test_release_blocks_without_confirm` | gọi trực tiếp node git_release không qua human_confirm → validator chặn từ compile |
| `test_custom_agent_inserted` | graph có `@security_checker` giữa dev và tester → chạy đúng thứ tự |
| `test_missing_marker_followup` | agent quên marker → gửi prompt bổ sung → nhận route |
| `test_max_iterations` | tester fail 6 lần → interrupt human_input |
| `test_workspace_queue` | 2 ticket thuộc 2 workflow khác nhau của cùng project → ticket 2 xếp hàng, tự chạy sau khi ticket 1 xong |
| `test_ticket_uses_snapshot` | sửa + xuất bản lại workflow khi ticket đang WAITING → ticket vẫn chạy theo version cũ; ticket mới dùng version mới |
| `test_auto_start_on_create` | `POST /workflows/{wid}/tickets` → ticket chuyển RUNNING và có event `agent_turn_start` của node đầu |
| `test_ws_replay` | connect WS với `after_seq` → nhận đúng các event thiếu |
| `test_notification_lifecycle` | tester pass → thông báo `CONFIRM` (1 bản dù node chạy lại) → confirm(approved=true) → `resolved_at` set, outcome APPROVED; BA hỏi lại → `INPUT` → reply → ANSWERED; cancel khi đang chờ → CANCELLED |
| `test_agent_restart_midturn` | sửa cấu hình @developer khi đang chạy → session cũ bị cancel/close, node chạy lại với session mới (config_version mới), có event `agent_restarted` và dòng log `↻ …` |
| `test_message_with_attachments` | gửi tin kèm 2 file → file nằm trong thư mục đính kèm, prompt lượt sau chứa đường dẫn, `git_release` không commit chúng |
| `test_api_agent_text_only` | agent `openai-api` làm node review: prompt chứa git diff đã cắt, không có tools; kết quả dạng văn bản + marker route; `modified_files` không đổi; không thể đặt vào `git_release` (validator) |
| `test_restart_resume` | tạo runner mới (giả lập restart) → confirm ticket đang WAITING_USER_CONFIRM vẫn chạy được |

## 13. Definition of Done
- [ ] Toàn bộ test engine pass (không cần CLI thật).
- [ ] Chạy thật trên bản copy của `HNBG_DEV` (marker `real_acp`): luồng Start → @ba → @developer → @tester → confirm → @leader push lên một remote test thành công.
- [ ] @developer cố `git commit` → bị chặn, event `permission` allowed=false hiển thị trong log.
- [ ] Không còn đường nào để LLM tự chạy `git push`.
