import { create } from "zustand";
import type { DraftFile } from "@/components/ticket-chat/types";
export const useChatDrafts = create<{
  files: Record<string, DraftFile[]>;
  text: Record<string, string>;
  setFiles: (key: string, files: DraftFile[]) => void;
  setText: (key: string, text: string) => void;
}>((set) => ({
  files: {},
  text: {},
  setFiles: (key, files) =>
    set((s) => ({ files: { ...s.files, [key]: files } })),
  setText: (key, text) => set((s) => ({ text: { ...s.text, [key]: text } })),
}));
