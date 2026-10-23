import { cookies } from "next/headers";
import WebSocket from "ws";
import { backendUrl, sessionCookie } from "@/lib/server-api";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const token = (await cookies()).get(sessionCookie)?.value;
  if (!token) return new Response(null, { status: 401 });
  const channel =
    new URL(request.url).searchParams.get("channel") || "users/me";
  const channels = [...new Set(channel.split(","))];
  if (
    channels.length > 30 ||
    channels.some(
      (value) =>
        !/^(users\/me|(?:projects|tickets)\/[a-f0-9-]{36})$/.test(value),
    )
  )
    return new Response(null, { status: 400 });
  const after = Math.max(
    0,
    Number(new URL(request.url).searchParams.get("after_seq")) || 0,
  );
  const sockets: WebSocket[] = [];
  let heartbeat: ReturnType<typeof setInterval>;
  let closed = false;
  const cleanup = () => {
    if (closed) return;
    closed = true;
    clearInterval(heartbeat);
    sockets.forEach((socket) => socket.terminate());
  };
  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      for (const channel of channels) {
        const socket = new WebSocket(
          `${backendUrl.replace(/^http/, "ws")}/ws/${channel}?after_seq=${Math.floor(after)}`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        sockets.push(socket);
        socket.on("message", (data) => {
          try {
            if (JSON.parse(data.toString()).type === "ping") {
              socket.send(JSON.stringify({ type: "pong" }));
              return;
            }
          } catch {
            return;
          }
          if (!closed)
            controller.enqueue(
              encoder.encode(
                `data: ${JSON.stringify({ ...JSON.parse(data.toString()), channel })}\n\n`,
              ),
            );
        });
        socket.on("error", () => {
          if (!closed) {
            cleanup();
            controller.close();
          }
        });
        socket.on("close", () => {
          if (!closed) {
            cleanup();
            controller.close();
          }
        });
      }
      heartbeat = setInterval(() => {
        if (!closed) controller.enqueue(encoder.encode(": heartbeat\n\n"));
      }, 20000);
      request.signal.addEventListener("abort", () => {
        if (!closed) {
          cleanup();
          controller.close();
        }
      });
    },
    cancel: cleanup,
  });
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
