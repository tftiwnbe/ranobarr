<script lang="ts">
  import { Select } from "bits-ui";
  import { CaretDownIcon } from "phosphor-svelte";
  import type { SelectOption } from "./Select.types";

  interface Props {
    value?: string;
    options: SelectOption[];
    placeholder?: string;
    disabled?: boolean;
    id?: string;
    class?: string;
    onValueChange?: (value: string) => void;
  }

  let {
    value = $bindable(""),
    options,
    placeholder = "",
    disabled = false,
    id = undefined,
    class: className = "",
    onValueChange,
  }: Props = $props();

  const selectedLabel = $derived(
    options.find((option) => option.value === value)?.label ?? "",
  );
</script>

<Select.Root type="single" bind:value {disabled} {onValueChange}>
  <Select.Trigger id={id} class={`branch-select ${className}`.trim()}>
    {#if value && selectedLabel}
      <span class="branch-select-label">{selectedLabel}</span>
    {:else}
      <span class="branch-select-placeholder">{placeholder}</span>
    {/if}
    <span class="branch-select-caret" aria-hidden="true">
      <CaretDownIcon size={12} weight="bold" />
    </span>
  </Select.Trigger>

  <Select.Portal>
    <Select.Content class="branch-select-menu" sideOffset={4}>
      <Select.Viewport class="branch-select-viewport">
        {#each options as option (option.value)}
          <Select.Item
            value={option.value}
            label={option.label}
            class="branch-select-item"
          >
            {option.label}
          </Select.Item>
        {/each}
      </Select.Viewport>
    </Select.Content>
  </Select.Portal>
</Select.Root>
