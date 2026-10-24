import type { ChatEvent, RuntimeState } from "@/components/ticket-chat/types";
// The same-origin SSE bridge owns the authenticated backend WebSocket and answers ping/pong.
// Browser code never receives the httpOnly session token.
export class TicketSocket {
  private source?: EventSource;
  private timer?: ReturnType<typeof setTimeout>;
  private stopped = false;
  private attempt = 0;
  private pending: ChatEvent[] = [];
  private batchTimer?: ReturnType<typeof setTimeout>;
  constructor(
    private id: string,
    private after: () => number,
    private handlers: {
      event?: (event: ChatEvent) => void;
      events?: (events: ChatEvent[]) => void;
      snapshot: (state: RuntimeState) => void;
      connection: (value: "connecting" | "connected" | "reconnecting") => void;
    },
  ) {}
  private flush() {
    clearTimeout(this.batchTimer);
    this.batchTimer = undefined;
    if (!this.pending.length) return;
    const events = this.pending;
    this.pending = [];
    this.handlers.events?.(events);
  }
  connect() {
    if (this.stopped) return;
    this.handlers.connection(this.attempt ? "reconnecting" : "connecting");
    const source = new EventSource(
      `/api/events?channel=tickets/${this.id}&after_seq=${this.after()}&view=chat`,
    );
    this.source = source;
    source.onmessage = ({ data }) => {
      try {
        const frame = JSON.parse(data);
        this.attempt = 0;
        this.handlers.connection("connected");
        if (frame.type === "snapshot") {
          this.flush();
          this.handlers.snapshot(frame.state);
        }
        if (frame.type === "event") {
          if (this.handlers.events) {
            this.pending.push(frame.data);
            if (!this.batchTimer)
              this.batchTimer = setTimeout(() => this.flush(), 50);
          } else this.handlers.event?.(frame.data);
        }
      } catch {
        /* Replay recovers malformed frames after reconnect. */
      }
    };
    source.onerror = () => {
      this.flush();
      source.close();
      if (this.stopped) return;
      this.handlers.connection("reconnecting");
      this.timer = setTimeout(
        () => this.connect(),
        [1000, 2000, 5000, 10000][Math.min(this.attempt++, 3)],
      );
    };
  }
  close() {
    this.stopped = true;
    clearTimeout(this.timer);
    clearTimeout(this.batchTimer);
    this.pending = [];
    this.source?.close();
  }
}
