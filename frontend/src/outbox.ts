// Offline outbox for field reports. Reports that cannot be sent (no signal, server down) are
// kept on the device and retried later. Each report carries a client_id generated here, and the
// server treats a repeated client_id as the same report, so retries never create duplicates.
import { ApiError, createFieldReport } from "./api";
import type { FieldReportInput } from "./types";

const KEY = "mac.outbox";

export interface QueuedReport {
  payload: FieldReportInput;
  queuedAt: string;
  lastError?: string;
  needsAttention?: boolean; // the server refused it (e.g. validation); retrying will not help
}

export function newClientId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  // Fallback for non-secure contexts (plain http on a LAN address).
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function loadOutbox(): QueuedReport[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as QueuedReport[]) : [];
  } catch {
    return [];
  }
}

function save(items: QueuedReport[]): boolean {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
    return true;
  } catch {
    return false;
  }
}

/** Returns false if the device cannot store it (private mode, storage blocked). */
export function enqueue(payload: FieldReportInput, error?: string): boolean {
  return save([...loadOutbox(), { payload, queuedAt: new Date().toISOString(), lastError: error }]);
}

export function discard(clientId: string): void {
  save(loadOutbox().filter((q) => q.payload.client_id !== clientId));
}

/** A network failure (no response at all) or a server error is worth retrying. */
export const isRetryable = (e: unknown): boolean =>
  !(e instanceof ApiError) || e.status >= 500 || e.status === 429;

export interface FlushResult {
  sent: number;
  remaining: number;
  needsLogin: boolean;
}

let flushing: Promise<FlushResult> | null = null;

/** Try to send everything in the outbox, oldest first. Safe to call often. */
export function flushOutbox(): Promise<FlushResult> {
  flushing ??= (async () => {
    let sent = 0;
    let needsLogin = false;
    const items = loadOutbox();
    const kept: QueuedReport[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.needsAttention || needsLogin) {
        kept.push(item);
        continue;
      }
      try {
        await createFieldReport(item.payload);
        sent++;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          needsLogin = true;
          kept.push({ ...item, lastError: "Log in again to send" });
        } else if (isRetryable(e)) {
          // Still offline: keep this and everything after it for the next attempt.
          kept.push({ ...item, lastError: "Waiting for connection" }, ...items.slice(i + 1));
          break;
        } else {
          kept.push({ ...item, lastError: (e as Error).message, needsAttention: true });
        }
      }
    }
    // Merge with changes made while we were sending: keep new items, honour discards.
    const now = loadOutbox();
    const nowIds = new Set(now.map((q) => q.payload.client_id));
    const startIds = new Set(items.map((q) => q.payload.client_id));
    const merged = [
      ...kept.filter((q) => nowIds.has(q.payload.client_id)),
      ...now.filter((q) => !startIds.has(q.payload.client_id)),
    ];
    save(merged);
    return { sent, remaining: merged.length, needsLogin };
  })().finally(() => {
    flushing = null;
  });
  return flushing;
}
