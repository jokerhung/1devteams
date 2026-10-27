"use client";

import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";
import { toast } from "sonner";

type Permission = NotificationPermission | "unsupported" | "insecure";

function permission(): Permission {
  if (window.isSecureContext === false) return "insecure";
  if (typeof window.Notification !== "function") return "unsupported";
  return Notification.permission;
}

export function BrowserNotifications() {
  const [state, setState] = useState<Permission | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const update = () => setState(permission());
    update();
    window.addEventListener("focus", update);
    return () => window.removeEventListener("focus", update);
  }, []);
  const descriptions: Record<Permission, string> = {
    default:
      "Bật thông báo trình duyệt để nhận tin mới cả khi đang xem tab khác. Toast trong ứng dụng luôn được hiển thị.",
    granted:
      "Đã bật thông báo trình duyệt. Thông báo mới cũng xuất hiện dưới dạng toast trong ứng dụng.",
    denied:
      "Thông báo trình duyệt đang bị chặn. Hãy cho phép thông báo trong cài đặt trang của trình duyệt; toast trong ứng dụng vẫn hoạt động.",
    unsupported:
      "Trình duyệt này chưa hỗ trợ thông báo hệ thống. Thông báo mới vẫn hiển thị bằng toast trong ứng dụng.",
    insecure:
      "Mở ứng dụng qua HTTPS hoặc localhost để bật thông báo trình duyệt. Toast trong ứng dụng vẫn hoạt động.",
  };
  return (
    <section
      aria-label="Thông báo trình duyệt"
      className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-stone-200 bg-stone-50 p-4"
    >
      <BellRing
        size={18}
        className="shrink-0 text-stone-500"
        aria-hidden="true"
      />
      <p className="min-w-0 flex-1 text-xs leading-5 text-stone-600">
        {state ? descriptions[state] : "Đang kiểm tra quyền thông báo…"}
      </p>
      {state === "default" && (
        <button
          type="button"
          className="btn btn-light shrink-0"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const result = await Notification.requestPermission();
              setState(result);
              if (result === "granted")
                toast.success("Đã bật thông báo trình duyệt");
            } catch {
              toast.error(
                "Không bật được thông báo. Kiểm tra quyền của trình duyệt.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          Bật thông báo trình duyệt
        </button>
      )}
    </section>
  );
}
