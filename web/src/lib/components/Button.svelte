<script lang="ts">
  interface Props {
    variant?: "solid" | "ghost" | "outline";
    type?: "button" | "submit";
    href?: string | null;
    disabled?: boolean;
    loading?: boolean;
    onclick?: () => void;
    children: import("svelte").Snippet;
  }

  let {
    variant = "solid",
    type = "button",
    href = null,
    disabled = false,
    loading = false,
    onclick,
    children
  }: Props = $props();

  const styles = {
    solid:
      "border:1px solid var(--void-6);background:var(--void-5);color:var(--text);",
    ghost:
      "border:1px solid transparent;background:transparent;color:var(--text-soft);",
    outline:
      "border:1px solid var(--line);background:var(--void-2);color:var(--text-soft);"
  } as const;

  const baseStyle =
    "display:inline-flex;align-items:center;justify-content:center;gap:0.5rem;height:40px;padding:0 0.95rem;transition:all 160ms ease;text-transform:lowercase;";
</script>

{#if href}
  <a
    href={href}
    aria-disabled={disabled || loading}
    style={`${baseStyle}${styles[variant]}${disabled || loading ? "opacity:0.4;pointer-events:none;" : ""}`}
  >
    {#if loading}<span>...</span>{/if}
    {@render children()}
  </a>
{:else}
  <button
    {type}
    disabled={disabled || loading}
    onclick={onclick}
    style={`${baseStyle}${styles[variant]}${disabled || loading ? "opacity:0.4;" : ""}`}
  >
    {#if loading}<span>...</span>{/if}
    {@render children()}
  </button>
{/if}
