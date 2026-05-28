<script lang="ts">
  type Variant = "error" | "success" | "info";

  interface Props {
    variant?: Variant;
    title?: string;
    message: string;
  }

  let { variant = "info", title, message }: Props = $props();

  const palette = {
    error: {
      border: "var(--error)",
      bg: "var(--error-soft)",
      dot: "var(--error)",
      label: "alert"
    },
    success: {
      border: "var(--success)",
      bg: "var(--success-soft)",
      dot: "var(--success)",
      label: "ok"
    },
    info: {
      border: "var(--void-6)",
      bg: "var(--cosmic-soft)",
      dot: "var(--cosmic)",
      label: "info"
    }
  } as const;

  const config = $derived(palette[variant]);
</script>

<div
  style={`border-left: 3px solid ${config.border}; background: ${config.bg}; padding: 0.8rem 0.9rem;`}
  role={variant === "error" ? "alert" : "status"}
>
  <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.35rem;">
    <span
      style={`width:6px;height:6px;border-radius:999px;background:${config.dot};box-shadow:0 0 8px ${config.dot};display:inline-block;`}
    ></span>
    <span class="eyebrow">{title ?? config.label}</span>
  </div>
  <div class="muted" style="padding-left: 0.75rem;">{message}</div>
</div>
