# PHASE 5 — Workflow Builder kéo thả (kiểu Dify) với `@xyflow/react`

Triển khai và kiểm chứng: [PHASE_5_IMPLEMENTATION_NOTES.md](PHASE_5_IMPLEMENTATION_NOTES.md).

## 1. Mục tiêu
Một project có **nhiều workflow** — đây là bước 2 trong thứ tự Project → **Workflow** → Ticket → Chat. Phase này làm:
1. Danh sách workflow của project + **wizard tạo workflow** (`/projects/[id]/workflows`, `/projects/[id]/workflows/new`).
2. Trình kéo thả cho từng workflow (`/projects/[id]/workflows/[wid]/edit`): lưu JSON đúng schema Phase 2 §5 (bản nháp), validate trực tiếp, **Xuất bản** để workflow nhận ticket.
3. Chế độ xem **Pipeline đơn giản** (danh sách bước đánh số như mockup `view-workflow`).

## 2. Cấu trúc file
```text
src/app/(workspace)/projects/[id]/workflows/page.tsx          # danh sách workflow (dùng lại card ở Phase 4 §4.5)
src/app/(workspace)/projects/[id]/workflows/new/page.tsx      # wizard tạo workflow
src/app/(workspace)/projects/[id]/workflows/[wid]/edit/page.tsx
src/components/workflow/
├── CreateWorkflowWizard.tsx    # bước 1 thông tin, bước 2 chọn template, bước 3 mở canvas
├── WorkflowCard.tsx            # dùng ở trang project & danh sách
├── WorkflowEditor.tsx          # ReactFlowProvider + layout 3 cột
├── WorkflowToolbar.tsx         # breadcrumb Project / Workflow, version nháp & bản xuất bản, trạng thái valid, nút: Template, Auto-layout, Validate, Lưu, Xuất bản, chế độ xem
├── SidebarPalette.tsx          # khối điều khiển + danh sách agent hiệu lực (kéo vào canvas)
├── WorkflowCanvas.tsx          # <ReactFlow> + Background(dots) + Controls + MiniMap
├── NodeInspector.tsx           # panel phải: cấu hình node được chọn
├── PipelineView.tsx            # chế độ danh sách bước (read-only, theo mockup)
├── ValidationPanel.tsx         # danh sách lỗi, click → focus node
├── nodes/
│   ├── BaseNode.tsx            # khung chung: header icon+title, body, các Handle
│   ├── StartNode.tsx
│   ├── AgentNode.tsx
│   ├── ConditionNode.tsx
│   ├── HumanInputNode.tsx
│   ├── HumanConfirmNode.tsx
│   ├── GitReleaseNode.tsx
│   └── EndNode.tsx
├── edges/LabeledEdge.tsx       # nhãn theo sourceHandle: Pass/Fail/Cần thêm thông tin/Đủ STR/Đồng ý/Từ chối
├── store.ts                    # zustand: nodes, edges, selection, dirty, history (undo/redo)
├── serialize.ts                # ReactFlow state ⇄ WorkflowGraph (Phase 2 schema)
├── validate.ts                 # validate phía client (cùng luật với backend) để báo lỗi tức thì
├── templates.ts                # bugfix_default, bugfix_with_security_review
└── layout.ts                   # auto-layout bằng dagre (LR)
```
Cài thêm: `npm i dagre @types/dagre zundo` (zundo cho undo/redo zustand).

## 3. Bố cục (theo phong cách mockup: nền trắng, viền stone, canvas chấm)
```
┌ Toolbar: HNBG_DEV / Fix Bug (BUG) · nháp v12 · xuất bản v11 · ✔ Hợp lệ · [Mẫu ▾] [Sắp xếp] [Kiểm tra] [Lưu] [Xuất bản] [Canvas | Pipeline] ┐
├ Palette (w-64) ─────┬──────────── Canvas (dots #E7E5DA) ─────────────┬ Inspector (w-80) ┤
│ KHỐI ĐIỀU KHIỂN     │                                               │ Cấu hình node     │
│ ▶ Bắt đầu           │   [Start]→[@ba]→[@developer]→[@tester]→…     │                   │
│ ⑂ Điều kiện         │                                               │                   │
│ ✋ Hỏi người dùng   │                                               │                   │
│ ✔ Người dùng duyệt  │                                               │                   │
│ ⎇ Git Release       │                                               │                   │
│ ■ Kết thúc          │                                               │                   │
│ AGENT TRONG PROJECT │                                               │                   │
│ 🐝 @ba   Claude     │                                               │                   │
│ 🛠️ @developer …     │                                               │                   │
└─────────────────────┴───────────────────────────────────────────────┴───────────────────┘
```

## 4. Node UI chi tiết
| Node | Hiển thị | Handles |
|------|----------|---------|
| StartNode | viền emerald, “Người dùng tạo ticket”, `Input: title, description` | out: default |
| AgentNode | icon+`@handle` màu agent, `RuntimeBadge`, model (mono), 1 dòng mô tả, `PermissionBadges` (VD đỏ “Cấm: git commit/push” cho developer), chip routing | in; out theo `routing`: `none`→default; `ba`→`need_info` (trên), `ready` (phải); `tester`/`review`→`pass` (phải, xanh), `fail` (dưới, đỏ) |
| ConditionNode | biểu thức rút gọn | `true`, `false` |
| HumanInputNode | viền indigo, “Chờ người dùng trả lời” | in, out default |
| HumanConfirmNode | viền indigo đậm, nhãn “LangGraph Interrupt”, message | `approved` (xanh), `rejected` (đỏ) |
| GitReleaseNode | viền purple, `@leader`, “Review diff → commit → push”, remote/branch | `success`, `failed` (tùy chọn) |
| EndNode | xám | in |

Node đang có lỗi validate → viền đỏ + icon cảnh báo, tooltip nội dung lỗi.

## 5. Tương tác
- **Kéo thả từ palette**: `onDragStart` set `application/aiteams-node` = `{type, agent_id?}`; `onDrop` dùng `screenToFlowPosition` tạo node id `n_<nanoid(6)>`. Kéo agent → AgentNode với `routing` mặc định suy từ `role_key` (BA→`ba`, TESTER→`tester`, khác→`none`); agent có `can_git_release` → tạo GitReleaseNode.
- **Nối dây**: `isValidConnection` chặn: nối vào `start`; từ `end`; tự nối chính mình; một sourceHandle có nhiều hơn 1 cạnh; `git_release` không có `human_confirm` ở phía trước (cảnh báo, không chặn cứng — validator sẽ báo).
- **Inspector** theo node:
  - Agent: chọn agent (Select từ effective agents), routing (`none`/`ba`/`tester`/`review`), *Hướng dẫn bổ sung cho bước này* (textarea → `data.instructions`), giới hạn số vòng lặp (override `MAX_NODE_ITERATIONS`). Link “Sửa agent” mở Sheet của Phase 4.
  - HumanConfirm: nội dung câu hỏi (mặc định “Bạn xác nhận lỗi đã được sửa xong?”), nhãn nút đồng ý/từ chối.
  - HumanInput: gợi ý hiển thị trong ô chat.
  - Condition: builder biểu thức đơn giản (dropdown biến + toán tử + giá trị).
  - GitRelease: agent leader, `push` on/off (off = chỉ commit local).
- **Phím tắt**: Delete xoá, Ctrl+Z/Ctrl+Y undo/redo, Ctrl+S lưu, Ctrl+D nhân bản node.
- **Mẫu**: “Tải mẫu Fix Bug mặc định” → thay toàn bộ canvas (confirm nếu dirty) bằng template, map agent theo `role_key` trong effective agents (thiếu agent → node đỏ yêu cầu chọn). Mẫu thứ 2: chèn `@security_checker` (routing `review`) giữa developer và tester, `fail` quay về developer.
- **Auto-layout**: dagre rankdir `LR`, nodesep 60, ranksep 120.
- **Dirty guard**: rời trang khi chưa lưu → confirm.

## 6. Lưu / Validate / Xuất bản
- `serialize.ts` chỉ xuất `{id, type, position, data}` và `{id, source, target, sourceHandle}` + `viewport`.
- Validate client-side mỗi khi thay đổi (debounce 300ms) → `ValidationPanel`; nút **Lưu** luôn cho phép (lưu nháp được dù invalid) → `PUT /workflows/{wid}/graph`, backend trả `{current_version, is_valid, errors}` — hiển thị lỗi backend ưu tiên.
- **Xuất bản** (`POST /workflows/{wid}/publish`) chỉ enable khi đã lưu và `is_valid`. Dialog xác nhận: “Ticket mới của workflow này sẽ dùng phiên bản v12. N ticket đang chạy vẫn dùng phiên bản cũ.”
- Lần xuất bản đầu tiên thành công → toast + nút **Tạo ticket đầu tiên** (mở `CreateTicketDialog` Phase 4 §4.6 → sau khi tạo mở cửa sổ chat).
- Header hiển thị version nháp, version đã xuất bản, thời gian lưu cuối; có badge “Có thay đổi chưa xuất bản” khi `current_version > published_version`.

## 6b. Wizard tạo workflow (`CreateWorkflowWizard`)
1. **Thông tin**: Tên workflow (unique trong project), Prefix mã ticket (tự gợi ý từ tên: “Fix Bug” → `BUG`; validate `^[A-Z]{2,10}$`, không trùng trong project), Mô tả, Icon/màu.
2. **Chọn điểm bắt đầu**: *Trống* (chỉ Start + End) | *Fix Bug mặc định* | *Fix Bug + Security Review* | *Nhân bản từ workflow có sẵn* (dropdown workflow khác trong project). Template map agent theo `role_key` trong effective agents của project; thiếu agent → cảnh báo ngay ở bước này kèm link thêm AI Team vào project.
3. **Tạo** → `POST /projects/{id}/workflows` → chuyển sang canvas `/workflows/[wid]/edit` ở trạng thái Nháp.

Wizard được mở **chủ động** từ: nút “Tạo workflow” ở tổng quan project (kể cả “Tạo workflow đầu tiên” khi project trống), nút “+ Thêm workflow” trong cây sidebar, hoặc trang danh sách workflow. **Tạo project không tự mở wizard này** (Phase 4 §3.0). Thanh bước “1. Project › 2. Workflow › 3. Ticket › 4. Chat” hiển thị ở đầu wizard (đang ở bước 2). Nếu project chưa có agent hiệu lực (chưa thêm AI Team) → wizard hiện cảnh báo và liên kết “Thành viên & AI Team”; template không map được agent thì để node trống chờ chọn.

## 7. PipelineView (mockup `view-workflow`)
Tuyến tính hoá graph theo đường chính (start → … → end, ưu tiên nhánh `ready`/`pass`/`approved`), render danh sách thẻ đánh số:
`1 · @ba — Xác nhận kịch bản tái tạo lỗi (Step-by-step)` + mô tả + badge quyền `Read-only`, … `4 · @leader — Review & Git Commit / Push` badge `Git Push`. Dòng mô tả đầu trang: “Thư mục áp dụng: `D:\VETC\FE\HNBG_DEV` — Chỉ duy nhất **@leader** có quyền commit & push sau khi người dùng xác nhận.” Các nhánh phụ (fail → developer) hiển thị dạng ghi chú nhỏ “↺ Nếu chưa đạt quay lại bước 2”.

## 8. Component dùng lại ở Phase 6
Xuất `WorkflowReadonlyGraph` (canvas không cho sửa, `fitView`, nhận `nodeStatuses: Record<string, 'idle'|'running'|'done'|'waiting'|'failed'>` để tô màu: running = `ring-2 ring-blue-500 animate-pulse`, waiting = indigo pulse, done = viền emerald + ✔, failed = đỏ).

## 9. Test
- Unit (`serialize.test.ts`, `validate.test.ts`): round-trip template; thiếu nhánh `fail` → lỗi; git_release không qua human_confirm → lỗi; agent không thuộc project → lỗi.
- Playwright `workflow.spec.ts`: bắt đầu từ **project trống** (vừa tạo, chưa có team/workflow) → thêm *Core Bugfix Squad* ở “Thành viên & AI Team” → trong project HNBG_DEV tạo workflow *Fix Bug* (BUG) từ mẫu → Xuất bản; tạo workflow thứ 2 *Fix Bug + Security* (SEC) bằng nhân bản → kéo `@security_checker` vào giữa developer–tester, nối lại dây → Lưu → reload → sơ đồ giữ nguyên, version tăng → Xuất bản → sidebar hiển thị 2 workflow; prefix trùng `BUG` → báo lỗi; workflow nháp không có nút tạo ticket.

## 10. Definition of Done
- [x] Kéo thả, nối dây, xoá, undo/redo hoạt động mượt với ≥ 30 node.
- [x] JSON lưu khớp 100% schema backend; backend validate pass với template.
- [x] Một project tạo/sửa/xuất bản/lưu trữ được nhiều workflow độc lập; mỗi workflow có prefix ticket riêng.
- [x] Custom agent mới tạo ở Phase 4 xuất hiện ngay trong palette (sau khi thêm vào project).
- [x] PipelineView hiển thị đúng như mockup cho template mặc định.
