export type ToastVariant = "success" | "error" | "info" | "warning";

export interface ToastEntry {
  id: string;
  variant: ToastVariant;
  title?: string;
  message: string;
  duration: number;
}

let items = $state<ToastEntry[]>([]);

function remove(id: string) {
  items = items.filter((entry) => entry.id !== id);
}

function add(
  variant: ToastVariant,
  message: string,
  opts?: { title?: string; duration?: number }
): string {
  const id = Math.random().toString(36).slice(2, 9);
  const duration = opts?.duration ?? 4000;
  items = [...items.slice(-3), { id, variant, message, title: opts?.title, duration }];
  setTimeout(() => remove(id), duration);
  return id;
}

export const toastStore = {
  get items() {
    return items;
  }
};

export const toast = {
  success: (message: string, opts?: { title?: string; duration?: number }) =>
    add("success", message, opts),
  error: (message: string, opts?: { title?: string; duration?: number }) =>
    add("error", message, opts),
  info: (message: string, opts?: { title?: string; duration?: number }) =>
    add("info", message, opts),
  warning: (message: string, opts?: { title?: string; duration?: number }) =>
    add("warning", message, opts),
  dismiss: remove
};
