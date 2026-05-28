<script lang="ts">
  interface Props {
    eyebrow: string;
    title: string;
    actionLabel?: string;
    actionDisabled?: boolean;
    onAction?: (() => void) | undefined;
    children: import("svelte").Snippet;
  }

  let {
    eyebrow,
    title,
    actionLabel,
    actionDisabled = false,
    onAction,
    children
  }: Props = $props();
</script>

<section class="card">
  <div class="card-header">
    <div>
      <div class="eyebrow">{eyebrow}</div>
      <h2 class="card-title">{title}</h2>
    </div>
    {#if actionLabel}
      <button
        type="button"
        disabled={actionDisabled}
        onclick={onAction}
        style={`display:inline-flex;align-items:center;height:36px;padding:0 0.8rem;border:1px solid var(--line);background:var(--void-2);color:var(--text-soft);${actionDisabled ? "opacity:0.4;" : ""}`}
      >
        {actionLabel}
      </button>
    {/if}
  </div>
  {@render children()}
</section>
