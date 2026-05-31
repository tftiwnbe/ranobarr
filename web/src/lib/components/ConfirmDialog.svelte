<script lang="ts">
  import { Dialog } from "bits-ui";

  interface Props {
    open?: boolean;
    title: string;
    description?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    loading?: boolean;
    danger?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  }

  let {
    open = $bindable(false),
    title,
    description = "",
    confirmLabel = "confirm",
    cancelLabel = "cancel",
    loading = false,
    danger = false,
    onConfirm,
    onCancel,
  }: Props = $props();
</script>

<Dialog.Root
  bind:open
  onOpenChange={(value) => {
    if (!value) onCancel();
  }}
>
  <Dialog.Portal>
    <Dialog.Overlay class="confirm-overlay" />
    <Dialog.Content class="confirm-content">
      <div class="confirm-header">
        <Dialog.Title class="confirm-title">{title}</Dialog.Title>
      </div>

      {#if description}
        <div class="confirm-copy">
          <Dialog.Description class="confirm-description"
            >{description}</Dialog.Description
          >
        </div>
      {/if}

      <div class="confirm-actions">
        <button
          type="button"
          class="confirm-btn confirm-btn-ghost"
          onclick={onCancel}
          disabled={loading}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          class:danger
          class="confirm-btn confirm-btn-solid"
          onclick={onConfirm}
          disabled={loading}
        >
          {confirmLabel}
        </button>
      </div>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
