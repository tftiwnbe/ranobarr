<script lang="ts">
  import { fly } from "svelte/transition";
  import { toast, type ToastVariant } from "./toast-store.svelte";

  interface Props {
    id: string;
    variant: ToastVariant;
    title?: string;
    message: string;
    duration: number;
  }

  let { id, variant, title, message, duration }: Props = $props();

  const configs = {
    success: {
      dot: "var(--success)",
      label: "ok",
      border: "var(--success)"
    },
    error: {
      dot: "var(--error)",
      label: "alert",
      border: "var(--error)"
    },
    info: {
      dot: "var(--cosmic)",
      label: "info",
      border: "var(--void-6)"
    },
    warning: {
      dot: "#fbbf24",
      label: "warn",
      border: "#f59e0b"
    }
  } as const;

  const config = $derived(configs[variant]);
</script>

<div
  class="toast-item"
  in:fly={{ x: -16, duration: 220, opacity: 0 }}
  out:fly={{ x: -16, duration: 140, opacity: 0 }}
  role="status"
  aria-live="polite"
  style={`border-left-color:${config.border};`}
>
  <button type="button" class="toast-button" onclick={() => toast.dismiss(id)}>
    <div class="toast-body">
      <div class="toast-label-row">
        <span
          class="toast-dot"
          style={`background:${config.dot};box-shadow:0 0 8px ${config.dot};`}
        ></span>
        <span class="toast-label">{title ?? config.label}</span>
      </div>
      <p class="toast-message">{message}</p>
    </div>
  </button>

  <div class="toast-progress-shell">
    <div class="toast-progress" style={`animation-duration:${duration}ms;`}></div>
  </div>
</div>
