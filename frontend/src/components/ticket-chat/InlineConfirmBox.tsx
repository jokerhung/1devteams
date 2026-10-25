"use client";
import { eventDate } from "./time";
import { useState } from "react";
import { Modal } from "@/components/ui-app/primitives";
import type { Gate } from "./types";
export function RejectFeedbackDialog({
  onClose,
  onReject,
}: {
  onClose: () => void;
  onReject: (feedback: string) => Promise<void>;
}) {
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal title="Yêu cầu sửa lại" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!feedback.trim()) return;
          setBusy(true);
          try {
            await onReject(feedback.trim());
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          Điểm chưa đạt
          <textarea
            autoFocus
            required
            maxLength={100000}
            placeholder="Mô tả điểm chưa đạt để @developer sửa lại"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button className="btn btn-dark" disabled={busy || !feedback.trim()}>
          Gửi yêu cầu sửa lại
        </button>
      </form>
    </Modal>
  );
}
export function InlineConfirmBox({
  gate,
  active,
  canConfirm,
  onConfirm,
}: {
  gate: Gate;
  active: boolean;
  canConfirm: boolean;
  onConfirm: (approved: boolean, feedback?: string) => Promise<void>;
}) {
  const [reject, setReject] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div
      id={active ? "confirm-box" : undefined}
      data-testid="confirm-box"
      className="mt-3 max-w-2xl rounded-xl border border-[#DFDDD0] bg-[#F7F6EE] p-3 text-xs"
    >
      <p className="font-semibold">
        {String(gate.payload.message || "Bạn xác nhận lỗi đã được sửa xong?")}
      </p>
      <details className="my-2 text-stone-500">
        <summary className="cursor-pointer">File sẽ commit</summary>
        <ul className="mt-1 font-mono">
          {((gate.payload.modified_files || []) as string[]).map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      </details>
      {gate.resolved ? (
        <p>
          {gate.resolved.approved ? "Đã xác nhận" : "Đã yêu cầu sửa lại"} bởi{" "}
          {gate.resolved.user?.display_name || "người dùng"} lúc{" "}
          {eventDate(gate.resolved.at).toLocaleTimeString("vi-VN")}
        </p>
      ) : active ? (
        canConfirm ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              disabled={busy}
              className="btn btn-light"
              onClick={() => setReject(true)}
            >
              {String(gate.payload.rejected_label || "Chưa đạt, sửa lại")}
            </button>
            <button
              disabled={busy}
              className="btn btn-dark"
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await onConfirm(true);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              ✓{" "}
              {String(
                gate.payload.approved_label ||
                  "Xác nhận (Báo @devops Commit & Push Git)",
              )}
            </button>
          </div>
        ) : (
          <p>Đang chờ MAINTAINER xác nhận</p>
        )
      ) : (
        <p className="text-stone-500">Yêu cầu này đã kết thúc</p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-red-700">
          {error}
        </p>
      )}
      {reject && (
        <RejectFeedbackDialog
          onClose={() => setReject(false)}
          onReject={(feedback) => onConfirm(false, feedback)}
        />
      )}
    </div>
  );
}
