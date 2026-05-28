<script lang="ts">
  import ToastItem from "./ToastItem.svelte";
  import { toastStore } from "./toast-store.svelte";
</script>

<div class="toast-container" aria-live="polite" aria-label="Notifications">
  {#each toastStore.items as entry (entry.id)}
    <ToastItem
      id={entry.id}
      variant={entry.variant}
      title={entry.title}
      message={entry.message}
      duration={entry.duration}
    />
  {/each}
</div>
