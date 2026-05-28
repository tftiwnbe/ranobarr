<script lang="ts">
  export type TabItem = {
    value: string;
    label: string;
    count?: number;
  };

  interface Props {
    tabs: TabItem[];
    value: string;
    onValueChange?: (value: string) => void;
  }

  let { tabs, value, onValueChange }: Props = $props();
</script>

<div class="tabs" role="tablist">
  {#each tabs as tab (tab.value)}
    {@const isActive = value === tab.value}
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      tabindex={isActive ? 0 : -1}
      class:active={isActive}
      class="tab"
      onclick={() => onValueChange?.(tab.value)}
    >
      <span class="tab-label">{tab.label}</span>
      {#if tab.count !== undefined && tab.count > 0}
        <span class="tab-count">{tab.count}</span>
      {/if}
    </button>
  {/each}
</div>
