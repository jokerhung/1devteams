type TerminalWriter = {
  write: (data: string, callback: () => void) => void;
  reset: () => void;
};
type Chunk = { data: string; replay: boolean; reset?: boolean };

/** xterm emits protocol replies through onData while parsing output. Only live
 * output may send those replies back to the PTY; replay is display-only.
 * Serialize writes because xterm's parser and write callbacks are asynchronous.
 */
export class TerminalOutput {
  private queue: Chunk[] = [];
  private writing = false;
  private replaying = false;
  private disposed = false;
  private frame: number | undefined;

  constructor(private terminal: TerminalWriter) {}

  get acceptsInput() {
    return !this.replaying && !this.disposed;
  }

  write(data: string, replay = false) {
    if (this.disposed) return;
    this.queue.push({ data, replay });
    if (data.length <= 512 && !this.writing && this.frame === undefined)
      this.flush();
    else this.schedule();
  }

  reset() {
    if (this.disposed) return;
    this.queue = [{ data: "", replay: true, reset: true }];
    this.schedule();
  }

  private schedule() {
    if (this.disposed || this.frame !== undefined || !this.queue.length) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = undefined;
      this.flush();
    });
  }

  private flush() {
    if (this.writing || this.disposed) return;
    const next = this.queue.shift();
    if (!next) return;
    if (next.reset) {
      this.terminal.reset();
      this.flush();
      return;
    }
    const parts = [next.data];
    let size = next.data.length;
    while (
      this.queue.length &&
      !this.queue[0].reset &&
      this.queue[0].replay === next.replay &&
      size + this.queue[0].data.length <= 65536
    ) {
      const chunk = this.queue.shift()!;
      parts.push(chunk.data);
      size += chunk.data.length;
    }
    this.writing = true;
    this.replaying = next.replay;
    this.terminal.write(parts.join(""), () => {
      this.writing = false;
      this.replaying = false;
      this.schedule();
    });
  }

  dispose() {
    this.disposed = true;
    this.queue = [];
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
  }
}
