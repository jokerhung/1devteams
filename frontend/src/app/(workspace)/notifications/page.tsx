"use client";
import Link from "next/link";
import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Bell, CircleHelp } from "lucide-react";
import { apiFetch, send } from "@/lib/api";
import type { Notice, Page } from "@/lib/types";
import {
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
} from "@/components/ui-app/primitives";
function relativeTime(value: string) {
  const min = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 60000));
  return min < 1
    ? "Vừa xong"
    : min < 60
      ? `${min} phút trước`
      : min < 1440
        ? `${Math.floor(min / 60)} giờ trước`
        : `${Math.floor(min / 1440)} ngày trước`;
}
const outcomes: Record<string, string> = {
  APPROVED: "Đã xác nhận",
  REJECTED: "Đã từ chối, gửi lại @developer",
  ANSWERED: "Đã trả lời",
  CANCELLED: "Đã huỷ",
};
export default function NotificationsPage() {
  const client = useQueryClient();
  const [tab, setTab] = useState("open");
  const open = useInfiniteQuery({
    queryKey: ["notifications", "open"],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      apiFetch<Page<Notice>>(
        `/notifications?status=open${pageParam ? `&cursor=${pageParam}` : ""}`,
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
  });
  const resolved = useInfiniteQuery({
    queryKey: ["notifications", "resolved"],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      apiFetch<Page<Notice>>(
        `/notifications?status=resolved${pageParam ? `&cursor=${pageParam}` : ""}`,
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
  });
  const query = tab === "open" ? open : resolved;
  const items = (query.data?.pages.flatMap((p) => p.items) || []).filter(
    (item, index, array) => array.findIndex((n) => n.id === item.id) === index,
  );
  return (
    <>
      <PageHeader
        title="Thông báo"
        description="Các việc cần bạn tương tác: xác nhận kết quả, trả lời câu hỏi của agent. Thông báo được lưu lại sau khi xử lý."
      >
        <button
          className="btn btn-light"
          onClick={async () => {
            try {
              await send("/notifications/read-all");
              await client.invalidateQueries({ queryKey: ["notifications"] });
            } catch (e) {
              toast.error((e as Error).message);
            }
          }}
        >
          Đánh dấu đã đọc
        </button>
      </PageHeader>
      <div
        role="tablist"
        aria-label="Thông báo"
        className="mb-5 flex gap-5 border-b border-stone-200"
      >
        {[
          ["open", "Cần xử lý", open.data?.pages[0]?.total],
          ["resolved", "Đã xử lý", resolved.data?.pages[0]?.total],
        ].map(([value, label, total]) => (
          <button
            role="tab"
            aria-selected={tab === value}
            key={value}
            className={`border-b-2 px-1 pb-3 text-xs ${tab === value ? "border-stone-800 font-semibold" : "border-transparent text-stone-400"}`}
            onClick={() => {
              setTab(String(value));
            }}
          >
            {label}{" "}
            <span className="ml-1 rounded bg-stone-100 px-1.5 text-[10px]">
              {total || 0}
            </span>
          </button>
        ))}
      </div>
      <ErrorState error={query.error} />
      {query.isLoading ? (
        <Loading />
      ) : !items.length ? (
        <EmptyState>
          {tab === "open"
            ? "Không có gì cần xử lý 🎉"
            : "Chưa có thông báo đã xử lý."}
        </EmptyState>
      ) : (
        <div className="divide-y divide-stone-100">
          {items.map((n) => (
            <Link
              key={n.id}
              href={`/projects/${n.project_id}/workflows/${n.workflow_id}/tickets/${n.ticket_id}?focus=gate`}
              onClick={() => {
                send(`/notifications/${n.id}/read`)
                  .then(() =>
                    client.invalidateQueries({ queryKey: ["notifications"] }),
                  )
                  .catch((e) => toast.error(e.message));
              }}
              className="flex items-start gap-3 rounded-lg p-4 hover:bg-stone-50"
            >
              <span
                className={`mt-1 rounded-lg p-2 ${n.type === "CONFIRM" ? "bg-amber-50 text-amber-700" : "bg-sky-50 text-sky-700"}`}
              >
                {n.type === "CONFIRM" ? (
                  <Bell size={16} />
                ) : (
                  <CircleHelp size={16} />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-xs font-semibold">
                  {n.title}
                  {!n.is_read && (
                    <span
                      aria-label="Chưa đọc"
                      className="ml-2 inline-block size-1.5 rounded-full bg-amber-500"
                    />
                  )}
                </h2>
                <p className="mt-1 text-xs leading-relaxed text-stone-500">
                  {n.body}
                </p>
                <p className="mt-2 text-[11px] text-stone-400">
                  {n.project.name} / {n.workflow.name} / {n.ticket.code} ·{" "}
                  {n.ticket.title}
                </p>
                <time
                  title={new Date(n.created_at).toLocaleString("vi-VN")}
                  className="mt-1 block text-[10px] text-stone-400"
                >
                  {relativeTime(n.created_at)}
                </time>
              </div>
              <span
                className={`badge ${tab === "open" ? (n.type === "CONFIRM" ? "!bg-amber-50 !text-amber-800" : "!bg-sky-50 !text-sky-800") : "!bg-emerald-50 !text-emerald-700"}`}
              >
                {tab === "open"
                  ? n.type === "CONFIRM"
                    ? "Cần xác nhận"
                    : "Cần trả lời"
                  : `✓ ${outcomes[n.outcome || ""] || "Đã xử lý"}`}
              </span>
            </Link>
          ))}
        </div>
      )}
      {query.hasNextPage && (
        <button
          disabled={query.isFetchingNextPage}
          className="btn btn-light mt-4"
          onClick={async () => {
            try {
              await query.fetchNextPage();
            } catch (e) {
              toast.error((e as Error).message);
            }
          }}
        >
          Xem thêm
        </button>
      )}
    </>
  );
}
