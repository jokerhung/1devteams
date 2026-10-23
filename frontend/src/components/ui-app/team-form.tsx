"use client";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { send } from "@/lib/api";
import type { Agent, Team } from "@/lib/types";
import { LogoPicker, Modal, Logo } from "./primitives";
export function TeamForm({
  team,
  agents,
  onClose,
}: {
  team?: Team;
  agents: Agent[];
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [selected, setSelected] = useState(team?.agent_ids || []);
  const [icon, setIcon] = useState(team?.icon || "🐝");
  const [logo, setLogo] = useState(team?.logo_url || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal title={team ? "Sửa AI Team" : "Tạo AI Team"} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!selected.length) return;
          const data = Object.fromEntries(new FormData(e.currentTarget));
          setBusy(true);
          try {
            await send(
              team ? `/teams/${team.id}` : "/teams",
              { ...data, icon, logo_url: logo, agent_ids: selected },
              team ? "PATCH" : "POST",
            );
            await client.invalidateQueries({ queryKey: ["teams"] });
            await client.invalidateQueries({ queryKey: ["projects"] });
            toast.success("Đã lưu AI Team");
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <LogoPicker
          icon={icon}
          logo_url={logo}
          onChange={(i, l) => {
            setIcon(i);
            setLogo(l);
          }}
        />
        <label className="field">
          Tên AI Team
          <input required name="name" defaultValue={team?.name} />
        </label>
        <label className="field">
          Mô tả
          <textarea name="description" defaultValue={team?.description} />
        </label>
        <fieldset>
          <legend className="mb-3 text-xs font-medium">Chọn Agent</legend>
          <div className="grid grid-cols-2 gap-2">
            {agents
              .filter((a) => a.is_active || selected.includes(a.id))
              .map((a) => (
                <label
                  key={a.id}
                  className="flex items-center gap-2 rounded-lg border border-stone-200 p-2 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(a.id)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, a.id]
                          : selected.filter((id) => id !== a.id),
                      )
                    }
                  />
                  <Logo entity={a} size={24} />
                  {a.handle}
                </label>
              ))}
          </div>
        </fieldset>
        {!selected.length && (
          <p className="error">AI Team phải có ít nhất 1 agent.</p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-light" onClick={onClose}>
            Huỷ
          </button>
          <button disabled={busy || !selected.length} className="btn btn-dark">
            Lưu AI Team
          </button>
        </div>
      </form>
    </Modal>
  );
}
