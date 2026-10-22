# ACP spike — Windows, 22/10/2026

## Trạng thái

**Codex: đã xác minh end-to-end. Claude: đã xác minh initialize, session/new,
set model và cancel; chưa xác minh inference/đọc/ghi file do gateway local không chạy.**
Không xem các ô “chưa xác minh” bên dưới là kết quả thành công.

Môi trường: Windows x64, Python 3.12.14, Node.js 24.18.1, npm 11.16.0.
Các package được xác minh bằng `npm view ... version bin repository --json` và pin trong
`package.json` / `package-lock.json`. Không dùng các package cũ dưới scope `@zed-industries`.

| Hạng mục | claude-agent-acp | codex-acp |
|---|---|---|
| Package & version | `@agentclientprotocol/claude-agent-acp@0.94.0` | `@agentclientprotocol/codex-acp@2.2.2` |
| Binary và spawn | `node_modules/.bin/claude-agent-acp.cmd`, resolve bằng `shutil.which`, chạy `cmd.exe /d /c <binary>` | `node_modules/.bin/codex-acp.cmd`, cùng cách spawn; package mang theo Codex tương thích |
| protocolVersion trả về | `1` | `1` |
| agentCapabilities | `loadSession`; prompt `image`, `embeddedContext`; MCP `http`, `sse`; auth/logout, providers; session additionalDirectories/close/delete/fork/list/resume/systemPrompt override; `_meta.claudeCode.promptQueueing=true` | `loadSession`; prompt `image`, `embeddedContext`; MCP `http=true`, `sse=false`, `acp=false`; auth/logout, providers; session resume/list/close/delete/fork/additionalDirectories/subagents |
| session/new trả về models? | **Không có `models`**. Có `sessionId`, `modes`, `configOptions`; model nằm ở config option `id=model`, current `sonnet` trên máy này | **Có `models`**, `modes` và `configOptions`. `currentModelId=gpt-6.1-sol[medium]` trong lượt ghi nhận; danh sách model lấy động từ response |
| Cách set system prompt | `_meta.systemPrompt.append` được adapter chấp nhận khi tạo session. **Chưa xác minh tác dụng lên câu trả lời** vì prompt timeout. Adapter còn quảng bá field `systemPrompt` qua capability; không suy diễn rằng append là API ổn định | Đã **prepend** chỉ dẫn BA vào prompt đầu; câu trả lời thực tế có `AITEAMS_BA_SPIKE`. Chưa xác minh kênh system riêng qua ACP; không coi prepend là instruction có độ ưu tiên system |
| Cách set model | **`session/set_config_option`** với `{sessionId, configId:"model", value:"sonnet"}` trả `configOptions` thành công. Chưa xác minh model inference. Không dùng `session/set_model` mặc định cho bản này | `session/set_model` với `{sessionId, modelId:<currentModelId từ session/new>}` trả `{}` thành công, prompt tiếp theo chạy xong |
| Các sessionUpdate quan sát được | `available_commands_update`, `session_info_update` (lượt cancel). Có notification mở rộng `_auth/status_update` riêng, không phải sessionUpdate | `available_commands_update`, `session_info_update`, `agent_message_chunk`, `tool_call`, `tool_call_update`, `usage_update` |
| Agent gọi fs/* hay tự ghi file? | **Chưa xác minh**, không có tool chạy thành công trong prompt timeout | Không có request `fs/*` trong lượt này. Adapter tự tạo `hello.txt` qua lệnh PowerShell; host đọc lại đúng `hello from aiTeams` |
| Agent gọi terminal/* hay tự chạy Bash? | **Chưa xác minh** | Không có request `terminal/*`; adapter tự thực thi PowerShell. Tool update chứa terminal display content và `_meta.terminal_info` / `terminal_output_delta` / `terminal_exit`; đây không phải client terminal requests |
| request_permission: kind, rawInput | **Chưa quan sát**, không dựng payload giả | Có `sessionId`, `toolCall:{toolCallId,title:"Run command",kind:"execute",status:"pending",rawInput:{command,cwd}}`, `options` chứa `kind=allow_once`, `allow_always`, `reject_once`. Response lấy `optionId` từ đúng option `kind=allow_once` |
| session/cancel | Notification gửi khi prompt còn pending; nhận prompt response `stopReason="cancelled"`. Đã kiểm tra riêng dù gateway không chạy | Notification gửi sau 2 giây khi prompt còn pending; nhận `stopReason="cancelled"` |
| Permission mode kiểm tra | `default` (Manual); chưa có tool thực sự để chứng minh coverage | Mặc định máy này là `agent`, file/lệnh chạy **không hỏi client**. Chuyển `read-only` bằng `session/set_mode` trả `{}`; lệnh ghi file có xin quyền, lệnh đọc vẫn không xin quyền |

Full initialize và session/new response nằm trong fixture, gồm toàn bộ modes, models và
configOptions; bảng chỉ tóm tắt. Danh sách model/mode là ảnh chụp tại thời điểm chạy,
không phải catalog để hard-code trong ứng dụng.

Harness ghi riêng các `checks` trong summary: chọn model, prompt `end_turn`, nội dung file,
marker BA và cancellation trong khi pending. Full spike trả exit code khác 0 nếu bất kỳ
bước bắt buộc nào chưa xác minh, kể cả trường hợp file đã được tạo nhưng cancel thất bại.

## Bằng chứng và tái lập

- `backend/tests/fixtures/acp/codex.ndjson`: stdout thật của lượt thành công, gồm tool execution,
  permission request, kết quả prompt và cancel. File `.client.ndjson` cùng tên lưu chiều client gửi.
- `backend/tests/fixtures/acp/claude.ndjson`: stdout thật của lượt initialize/new/set model/cancel.
  **Không chứa phiên đọc/ghi file thành công**. File `.client.ndjson` cùng tên lưu chiều client gửi.
- IDs được thay ổn định, workspace thành `C:\spike\workspace`, user home và credential đã khử.
  Các NDJSON này không chứa log được dựng bằng tay.
- Raw stdout, stderr, summary và workspace path nằm trong `backend/spike_logs/` (gitignored);
  workspace thật nằm trong Windows Temp, không chạy agent trên working tree aiTeams.

```powershell
cd backend
uv run python scripts/acp_spike.py --runtime codex --mode read-only
uv run python scripts/acp_spike.py --runtime claude
uv run python scripts/acp_spike.py --runtime claude --cancel-only
```

Lượt Codex đầu thử thư mục con `spike_logs/` tạo file được nhưng host bị `PermissionError`
khi đọc lại. Sau đó đã đổi harness sang Windows Temp, chạy lại với `read-only` và kiểm tra
nội dung file thành công. Không thay ACL hoặc security settings của máy.

### Blocker Claude đã chẩn đoán

- `claude auth status` báo có credential, nhưng điều này không chứng minh gateway hoạt động.
- Process hiện kế thừa `ANTHROPIC_BASE_URL` trỏ gateway local **cổng 20128**.
- TCP connect tới cổng này thất bại; HTTP probe tới `/v1/messages` trả `ConnectError`.
- ACP vẫn initialize/new/set_config_option được nhưng `session/prompt` không sinh message/tool
  trong thời hạn 60–180 giây; `claude -p` trực tiếp cũng timeout sau 45 giây.
- Thử `--isolate-settings` để bỏ settings/hook cá nhân trong session vẫn timeout.
- Không sửa credential, cấu hình Claude cá nhân hoặc tự thay provider.

**Cần khởi động gateway Claude đã cấu hình, chạy lại full spike, xác minh BA marker,
hello.txt, permission và fs/terminal behavior rồi cập nhật bảng/fixture Claude trước khi
coi Phase 0 hoàn tất toàn bộ.**

## Các quyết định cho Phase 1

1. Hỗ trợ cả `models` lẫn `configOptions` để lấy model; ưu tiên capability/response thật.
   Claude 0.94.0 khác giả định `session/set_model` trong spec cũ.
2. Không xem tool-call notification là điểm chặn quyền: tool có thể đã chạy khi client nhận nó.
3. **Không thể enforce mọi lệnh chỉ bằng `session/request_permission` với mặc định hiện tại.**
   Codex `agent` đã tự ghi/chạy lệnh; `read-only` vẫn tự chạy lệnh đọc. Cần xác minh cấu hình
   approval ở runtime để tất cả thao tác thuộc profile đi qua guard, hoặc chặn runtime/profile
   không đáp ứng. Mode `read-only` một mình chưa đủ để bảo đảm `allow_terminal=false`.
4. Các handler fs/terminal trong harness phục vụ giao thức nếu được gọi; đây là code chẩn đoán,
   **không phải** permission guard/sandbox production. Phase 1 vẫn phải enforce path, command,
   profile và lifecycle như spec. Git release vẫn do backend thực thi theo master plan.
5. Reader phải tiếp tục xử lý response trong khi handler `terminal/wait_for_exit` đang chờ;
   dùng task riêng cho agent requests. Giữ stdout, stderr tách biệt, NDJSON limit 16 MiB,
   reject pending futures khi EOF và dừng process tree khi cleanup trên Windows.

## Kiểm tra skeleton

- `GET /api/health`: HTTP 200, `{status:"ok",acp:{claude:true,codex:true}}` trên máy đích.
- `scripts/dev.ps1 -SmokeTest`: backend + frontend khởi động, trang `/` HTTP 200 và tự dừng cả hai.
- Ruff check/format, mypy và pytest health (4 tổ hợp binary): pass.
- Frontend ESLint, TypeScript và production build Next.js 15.5.28: pass.
- Chưa xác nhận visual bằng browser automation: connector trả `Codex auth token is unavailable`.
  HTTP/HTML và production build đã được kiểm tra; không coi đó là visual/browser test.
- `npm audit` còn advisory dependency upstream (`braces` qua eslint/shadcn và `postcss`
  bundled trong Next 15); `npm audit fix` không xử lý được trong major đang chọn.
  Không tự nâng Next 16 trái master plan; cần xử lý trước giai đoạn hardening/release.

## Nguồn

- [Claude ACP repository](https://github.com/agentclientprotocol/claude-agent-acp)
- [Codex ACP repository](https://github.com/agentclientprotocol/codex-acp)
- [ACP protocol](https://agentclientprotocol.com/protocol/overview)
- Metadata/npm và mã source của đúng hai package đã pin trong repo là căn cứ cho thay đổi API nêu trên.
