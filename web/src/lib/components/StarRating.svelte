<script lang="ts">
  import { StarIcon } from "phosphor-svelte";

  interface Props {
    value?: number | null;
    size?: number;
  }

  let { value = 0, size = 12 }: Props = $props();

  const safeValue = $derived(Math.max(0, Math.min(5, value ?? 0)));
</script>

<div class="rating-stars" aria-label={`rating ${safeValue} of 5`}>
  {#each [1, 2, 3, 4, 5] as level (level)}
    {@const filled = safeValue >= level}
    <StarIcon size={size} weight={filled ? "fill" : "regular"} class={`rating-star ${filled ? "filled" : ""}`.trim()} />
  {/each}
</div>
