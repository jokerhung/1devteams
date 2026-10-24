"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <section className="w-full max-w-sm rounded-2xl border border-stone-300 bg-white p-8 shadow-sm">
        <div className="mb-7">
          <span className="text-3xl">🐝</span>
          <h1 className="mt-3 text-xl font-bold">Chào mừng đến aiTeams</h1>
          <p className="mt-2 text-xs text-stone-500">
            Đăng nhập để mở workspace của bạn.
          </p>
        </div>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            setBusy(true);
            setError("");
            try {
              const response = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(Object.fromEntries(form)),
              });
              const result = await response.json();
              if (!response.ok)
                throw new Error(
                  result.detail?.detail ||
                    result.detail?.message ||
                    result.detail ||
                    "Không thể đăng nhập",
                );
              toast.success("Đăng nhập thành công");
              router.replace("/");
              router.refresh();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="field">
            Tài khoản hoặc email
            <input name="email" type="text" autoComplete="username" required />
          </label>
          <label className="field">
            Mật khẩu
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="btn btn-dark w-full" disabled={busy}>
            {busy ? "Đang đăng nhập…" : "Đăng nhập"}
          </button>
        </form>
      </section>
    </main>
  );
}
