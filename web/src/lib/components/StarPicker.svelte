<script lang="ts">
  import { StarIcon } from "phosphor-svelte";

  interface Props {
    value?: number;
    size?: number;
    onChange: (value: number) => void;
  }

  let { value = 0, size = 18, onChange }: Props = $props();

  let hoverValue = $state(0);

  const activeValue = $derived(hoverValue > 0 ? hoverValue : value);

  function pick(level: number) {
    onChange(value === level ? 0 : level);
  }
</script>

<div class="star-picker" role="radiogroup" aria-label="title rating">
  {#each [1, 2, 3, 4, 5] as level (level)}
    {@const filled = activeValue >= level}
    <button
      type="button"
      class="star-picker-btn"
      aria-label={`${level} stars`}
      aria-pressed={value === level}
      onmouseenter={() => {
        hoverValue = level;
      }}
      onmouseleave={() => {
        hoverValue = 0;
      }}
      onfocus={() => {
        hoverValue = level;
      }}
      onblur={() => {
        hoverValue = 0;
      }}
      onclick={() => {
        pick(level);
      }}
    >
      <StarIcon
        size={size}
        weight={filled ? "fill" : "regular"}
        class={`star-picker-icon ${filled ? "filled" : ""}`.trim()}
      />
    </button>
  {/each}
</div>
