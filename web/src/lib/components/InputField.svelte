<script lang="ts">
  interface Props {
    label: string;
    value: string;
    placeholder?: string;
    type?: string;
    rows?: number;
    multiline?: boolean;
  }

  let {
    label,
    value = $bindable(""),
    placeholder = "",
    type = "text",
    rows = 3,
    multiline = false
  }: Props = $props();
</script>

<label class="stack" style="gap:0.35rem;">
  <span class="eyebrow">{label}</span>
  {#if multiline}
    <textarea
      bind:value
      {rows}
      {placeholder}
      style="width:100%;min-height:92px;padding:0.9rem 1rem;border:1px solid var(--line);background:var(--void-2);color:var(--text);resize:vertical;"
    ></textarea>
  {:else}
    <input
      bind:value
      {type}
      {placeholder}
      style="width:100%;height:48px;padding:0 1rem;border:1px solid var(--line);background:var(--void-2);color:var(--text);"
    />
  {/if}
</label>
