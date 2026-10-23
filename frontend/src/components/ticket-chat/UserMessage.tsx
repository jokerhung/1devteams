import { eventDate } from "./time";
import type { Agent } from "@/lib/types";
import type { ChatEvent, Attachment } from "./types";
import { MarkdownContent } from "./blocks/MarkdownContent";
import { MessageAttachments } from "./MessageAttachments";
export function UserMessage({
  event,
  agents,
}: {
  event: ChatEvent;
  agents: Agent[];
}) {
  return (
    <article
      aria-label={`Tin nhắn ${event.sender_name}`}
      className="flex gap-3 py-2"
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-stone-800 text-xs text-white">
        {event.sender_name
          .trim()
          .split(/\s+/)
          .map((p) => p[0])
          .slice(0, 2)
          .join("")}
      </span>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex gap-2 text-xs">
          <b>{event.sender_name}</b>
          <time className="text-[11px] text-stone-400">
            {eventDate(event.created_at).toLocaleTimeString("vi-VN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </time>
        </div>
        <MarkdownContent text={event.content} agents={agents} />
        <MessageAttachments
          files={(event.metadata.attachments || []) as Attachment[]}
        />
      </div>
    </article>
  );
}
