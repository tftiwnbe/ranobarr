<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { DotsThreeOutlineVerticalIcon } from "phosphor-svelte";
  import Select from "./lib/components/Select.svelte";
  import type { SelectOption } from "./lib/components/Select.types";
  import StarField from "./lib/components/StarField.svelte";
  import ToastContainer from "./lib/components/ToastContainer.svelte";
  import { toast } from "./lib/components/toast-store.svelte";
  import {
    type BranchSummary,
    createTrackedBook,
    createCollection,
    deleteCollection,
    deleteTrackedBook,
    getCredential,
    listCollections,
    latestArtifact,
    listJobs,
    listTrackedBooks,
    previewTrackedBook,
    putCredential,
    triggerCheck,
    updateBookPreferences,
    updateTrackedBookBranch,
    validateCredential,
    type ArtifactSummary,
    type CollectionSummary,
    type CredentialValidation,
    type CredentialView,
    type JobSummary,
    type NamedTagSummary,
    type PreviewBook,
    type TrackedBook,
  } from "./lib/api";

  type BookCard = TrackedBook & { latestArtifact: ArtifactSummary | null };

  // ─── State ───────────────────────────���────────────────
  let books = $state<BookCard[]>([]);
  let jobs = $state<JobSummary[]>([]);
  let collections = $state<CollectionSummary[]>([]);
  let credential = $state<CredentialView | null>(null);
  let validation = $state<CredentialValidation | null>(null);

  let loading = $state(true);
  let submitting = $state(false);
  let validating = $state(false);
  let previewing = $state(false);
  let actionBookId = $state<string | null>(null);
  let savingPreferences = $state(false);
  let savingCollection = $state(false);

  // Form fields
  let accessToken = $state("");
  let refreshToken = $state("");
  let bookUrl = $state("");
  let selectedBranchId = $state("");
  let preview = $state<PreviewBook | null>(null);
  let collectionName = $state("");
  let collectionDescription = $state("");

  // UI state
  let drawerOpen = $state(false);
  let drawerClosing = $state(false);
  let drawerTab = $state<"track" | "auth" | "jobs" | "library" | "book">("track");
  let drawerBookId = $state<string | null>(null);
  let searchQuery = $state("");
  let sortMode = $state<"title" | "updated" | "added">("updated");
  let filterOpen = $state(false);
  let filterHasEpub = $state(false);
  let filterFavorites = $state(false);
  let filterCurrent = $state(false);
  let filterCollectionId = $state("");
  let drawerCloseTimer: ReturnType<typeof setTimeout> | null = null;
  let preferenceVisibleGenres = $state<string[]>([]);
  let preferenceVisibleTags = $state<string[]>([]);
  let preferenceCollectionIds = $state<string[]>([]);
  let preferenceIsFavorite = $state(false);
  let preferenceIsCurrent = $state(false);
  let preferenceRating = $state("");
  let preferenceComment = $state("");

  // ─── Derived ─────���───────────────────�─────────────────
  const runningJobs = $derived(
    jobs.filter((j) => j.status === "running").length,
  );
  const failedJobs = $derived(jobs.filter((j) => j.status === "failed").length);
  const syncStateByBook = $derived.by(() => {
    const states = new Map<string, "running" | "queued">();
    for (const job of jobs) {
      if (!job.book_id) continue;
      if (job.type !== "check_updates" && job.type !== "build_artifact") continue;
      if (job.status !== "running" && job.status !== "queued") continue;
      if (!states.has(job.book_id)) {
        states.set(job.book_id, job.status === "running" ? "running" : "queued");
      }
    }
    return states;
  });

  const currentBook = $derived(
    books.find((book) => book.is_current) ?? null,
  );
  const favoriteCount = $derived(books.filter((book) => book.is_favorite).length);

  const filteredBooks = $derived.by(() => {
    let result = books.slice();

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (b) =>
          b.title.toLowerCase().includes(q) ||
          (b.author ?? "").toLowerCase().includes(q),
      );
    }

    if (filterHasEpub) {
      result = result.filter((b) => b.latestArtifact !== null);
    }
    if (filterFavorites) {
      result = result.filter((b) => b.is_favorite);
    }
    if (filterCurrent) {
      result = result.filter((b) => b.is_current);
    }
    if (filterCollectionId) {
      result = result.filter((b) => b.collections.some((collection) => collection.id === filterCollectionId));
    }

    result.sort((a, b) => {
      let cmp = 0;
      if (sortMode === "title") {
        cmp = a.title.localeCompare(b.title);
      } else if (sortMode === "updated") {
        const da = a.updated_at ? new Date(a.updated_at).getTime() : 0;
        const db = b.updated_at
          ? new Date(b.updated_at).getTime()
          : 0;
        cmp = db - da;
      } else if (sortMode === "added") {
        const da = a.created_at ? new Date(a.created_at).getTime() : 0;
        const db = b.created_at ? new Date(b.created_at).getTime() : 0;
        cmp = db - da;
      }
      return cmp;
    });

    return result;
  });

  const drawerBook = $derived(
    drawerBookId ? books.find((book) => book.book_id === drawerBookId) ?? null : null,
  );

  // ─── Data loading ───────────────────���──────────────────
  async function loadDashboard() {
    loading = true;
    try {
      credential = await getCredential();
      accessToken = "";
      refreshToken = "";
      const [trackedBooks, recentJobs, libraryCollections] = await Promise.all([
        listTrackedBooks("updated"),
        listJobs(),
        listCollections(),
      ]);
      const artifactPairs = await Promise.all(
        trackedBooks.map(async (book) => ({
          bookId: book.book_id,
          artifact: await latestArtifact(book.book_id),
        })),
      );
      const artifactMap = new Map(
        artifactPairs.map((e) => [e.bookId, e.artifact]),
      );
      books = trackedBooks.map((book) => ({
        ...book,
        latestArtifact: artifactMap.get(book.book_id) ?? null,
      }));
      jobs = recentJobs.slice(0, 20);
      collections = libraryCollections;
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to load dashboard",
      );
    } finally {
      loading = false;
    }
  }

  // ─── Actions ──────────────────────���───────────────────
  async function saveCredential() {
    submitting = true;
    try {
      credential = await putCredential({
        access_token: accessToken.trim() || null,
        refresh_token: refreshToken.trim() || null,
      });
      toast.success("stored ranobelib credentials");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to store credentials",
      );
    } finally {
      submitting = false;
    }
  }

  async function runValidation() {
    validating = true;
    try {
      validation = await validateCredential();
      if (validation.valid) {
        toast.success("credential validated against ranobelib");
      } else {
        toast.warning(validation.error ?? "credential check failed");
      }
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "failed to validate credentials",
      );
    } finally {
      validating = false;
    }
  }

  function clearPreview() {
    preview = null;
    selectedBranchId = "";
  }

  async function inspectBookUrl() {
    if (!bookUrl.trim()) return;
    previewing = true;
    try {
      preview = await previewTrackedBook(bookUrl.trim());
      selectedBranchId = "";
    } catch (error) {
      clearPreview();
      toast.error(
        error instanceof Error ? error.message : "failed to inspect title",
      );
    } finally {
      previewing = false;
    }
  }

  async function submitBook() {
    if (!preview) {
      await inspectBookUrl();
      if (!preview) return;
    }
    submitting = true;
    try {
      await createTrackedBook({
        url: bookUrl.trim(),
        branch_mode: selectedBranchId ? "selected" : "default",
        selected_branch_id: selectedBranchId || null,
      });
      bookUrl = "";
      clearPreview();
      closeDrawer();
      toast.success("title queued for sync and epub build");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to track title",
      );
    } finally {
      submitting = false;
    }
  }

  async function runBookAction(bookId: string) {
    actionBookId = bookId;
    try {
      await triggerCheck(bookId);
      toast.success("queued sync and rebuild");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to sync title",
      );
    } finally {
      actionBookId = null;
    }
  }

  async function changeBookBranch(bookId: string, branchId: string | null) {
    actionBookId = bookId;
    try {
      await updateTrackedBookBranch(bookId, branchId);
      toast.success("queued branch sync");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to update branch",
      );
    } finally {
      actionBookId = null;
    }
  }

  async function removeBook(book: BookCard) {
    const confirmed = window.confirm(`Delete "${book.title}" and its stored files?`);
    if (!confirmed) return;

    actionBookId = book.book_id;
    try {
      await deleteTrackedBook(book.book_id);
      closeDrawer();
      toast.success("title removed");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to delete title",
      );
    } finally {
      actionBookId = null;
    }
  }

  async function saveBookPreferences() {
    if (!drawerBook) return;
    savingPreferences = true;
    try {
      await updateBookPreferences(drawerBook.book_id, {
        opds_visible_genre_slugs: preferenceVisibleGenres,
        opds_visible_tag_slugs: preferenceVisibleTags,
        is_favorite: preferenceIsFavorite,
        is_current: preferenceIsCurrent,
        rating: preferenceRating ? Number(preferenceRating) : null,
        comment: preferenceComment.trim() || null,
        collection_ids: preferenceCollectionIds,
      });
      toast.success("saved title preferences");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to save title preferences",
      );
    } finally {
      savingPreferences = false;
    }
  }

  async function createLibraryCollection() {
    if (!collectionName.trim()) return;
    savingCollection = true;
    try {
      await createCollection({
        name: collectionName.trim(),
        description: collectionDescription.trim() || null,
      });
      collectionName = "";
      collectionDescription = "";
      toast.success("collection created");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to create collection",
      );
    } finally {
      savingCollection = false;
    }
  }

  async function removeCollection(collection: CollectionSummary) {
    const confirmed = window.confirm(`Delete collection "${collection.name}"?`);
    if (!confirmed) return;
    try {
      await deleteCollection(collection.id);
      toast.success("collection removed");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to delete collection",
      );
    }
  }

  // ─── Helpers ─────────────────────────���────────────────
  function artifactUrl(book: BookCard): string | null {
    return book.latestArtifact
      ? `/api/v1/artifacts/${book.latestArtifact.id}/download`
      : null;
  }

  function formatDate(value: string | null): string {
    if (!value) return "never";
    const d = new Date(value);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function formatBytes(value: number): string {
    if (value < 1024) return `${value} b`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} kb`;
    return `${(value / (1024 * 1024)).toFixed(1)} mb`;
  }

  function setSort(mode: typeof sortMode) {
    sortMode = mode;
  }

  function openDrawer(tab: typeof drawerTab) {
    if (drawerCloseTimer) {
      clearTimeout(drawerCloseTimer);
      drawerCloseTimer = null;
    }
    drawerTab = tab;
    drawerOpen = true;
    drawerClosing = false;
  }

  function openBookDrawer(bookId: string) {
    drawerBookId = bookId;
    openDrawer("book");
  }

  function closeDrawer() {
    if (!drawerOpen || drawerClosing) return;
    drawerClosing = true;
    drawerCloseTimer = setTimeout(() => {
      drawerOpen = false;
      drawerClosing = false;
      if (drawerTab === "book") {
        drawerBookId = null;
      }
      drawerCloseTimer = null;
    }, 300);
  }

  function coverUrl(book: Pick<BookCard, "book_id" | "cover_url">): string | null {
    return book.cover_url ? `/opds/books/${book.book_id}/cover` : null;
  }

  function branchSelectValue(book: Pick<BookCard, "selected_branch_id">): string {
    return book.selected_branch_id ?? "";
  }

  function branchOptionLabel(branch: BranchSummary): string {
    return branch.display;
  }

  function branchOptions(branches: BranchSummary[]): SelectOption[] {
    return [
      { value: "", label: "default branch" },
      ...branches.map((branch) => ({
        value: branch.id,
        label: branchOptionLabel(branch),
      })),
    ];
  }

  function collectionFilterOptions(items: CollectionSummary[]): SelectOption[] {
    return [
      { value: "", label: "all collections" },
      ...items.map((collection) => ({
        value: collection.id,
        label: collection.name,
      })),
    ];
  }

  const ratingOptions: SelectOption[] = [
    { value: "", label: "no rating" },
    { value: "1", label: "1 / 5" },
    { value: "2", label: "2 / 5" },
    { value: "3", label: "3 / 5" },
    { value: "4", label: "4 / 5" },
    { value: "5", label: "5 / 5" },
  ];

  function bookSyncLabel(bookId: string): string | null {
    const state = syncStateByBook.get(bookId);
    if (!state) return null;
    return state === "running" ? "syncing" : "queued";
  }

  function toggleSlugValue(values: string[], slug: string) {
    return values.includes(slug)
      ? values.filter((value) => value !== slug)
      : [...values, slug];
  }

  function toggleNamedValue(kind: "genre" | "tag", item: NamedTagSummary) {
    if (kind === "genre") {
      preferenceVisibleGenres = toggleSlugValue(preferenceVisibleGenres, item.slug);
      return;
    }
    preferenceVisibleTags = toggleSlugValue(preferenceVisibleTags, item.slug);
  }

  function toggleCollectionValue(collectionId: string) {
    preferenceCollectionIds = toggleSlugValue(preferenceCollectionIds, collectionId);
  }

  function syncDrawerBookPreferences(book: BookCard | null) {
    if (!book) return;
    preferenceVisibleGenres = book.opds_visible_genres.map((item) => item.slug);
    preferenceVisibleTags = book.opds_visible_tags.map((item) => item.slug);
    preferenceCollectionIds = book.collections.map((item) => item.id);
    preferenceIsFavorite = book.is_favorite;
    preferenceIsCurrent = book.is_current;
    preferenceRating = book.rating ? String(book.rating) : "";
    preferenceComment = book.comment ?? "";
  }

  onMount(loadDashboard);
  $effect(() => {
    syncDrawerBookPreferences(drawerBook);
  });
  onDestroy(() => {
    if (drawerCloseTimer) {
      clearTimeout(drawerCloseTimer);
    }
  });
</script>

<svelte:head>
  <title>ranobarr</title>
  <meta
    name="description"
    content="Track RanobeLib titles and build EPUB artifacts."
  />
  <meta
    name="viewport"
    content="width=device-width, initial-scale=1, viewport-fit=cover"
  />
</svelte:head>

<div class="page-shell">
  <StarField count={54} />
  <div class="grid-overlay"></div>

  <!-- ─── Header ─────────────────────────────── -->
  <header class="app-header">
    <div class="app-logo">
      <span class="app-logo-name">ranobarr</span>
      <span class="app-logo-sub">/ ranobe tracker</span>
    </div>

    <div class="header-stats">
      {#if currentBook}
        <div class="stat-pill">
          <span class="stat-pill-value">1</span>
          <span>current</span>
        </div>
      {/if}
      {#if favoriteCount > 0}
        <div class="stat-pill">
          <span class="stat-pill-value">{favoriteCount}</span>
          <span>favorites</span>
        </div>
      {/if}
      {#if runningJobs > 0}
        <div class="stat-pill stat-pill--running">
          <span class="stat-pill-value">{runningJobs}</span>
          <span>running</span>
        </div>
      {/if}
      {#if failedJobs > 0}
        <div class="stat-pill stat-pill--error">
          <span class="stat-pill-value">{failedJobs}</span>
          <span>failed</span>
        </div>
      {/if}
      <div class="stat-pill">
        <span class="stat-pill-value">{books.length}</span>
        <span>titles</span>
      </div>
    </div>
  </header>

  <!-- ─── Main ��───────────────────────────── -->
  <main class="page-body">
    <!-- Toolbar -->
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-icon">⌕</span>
        <input
          class="search-input"
          type="search"
          placeholder="search titles..."
          bind:value={searchQuery}
        />
      </div>

      <button
        type="button"
        class="sort-btn"
        class:active={sortMode === "title"}
        onclick={() => setSort("title")}
        title="Sort by title"
      >title</button>

      <button
        type="button"
        class="sort-btn"
        class:active={sortMode === "updated"}
        onclick={() => setSort("updated")}
        title="Sort by update date"
      >updated</button>

      <button
        type="button"
        class="sort-btn"
        class:active={sortMode === "added"}
        onclick={() => setSort("added")}
        title="Sort by add date"
      >added</button>

      <button
        type="button"
        class="filter-btn"
        class:active={filterOpen}
        onclick={() => {
          filterOpen = !filterOpen;
        }}
        title="Filters"
        aria-label="Toggle filters"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 6h16l-6.25 7.2v4.95l-3.5 1.9v-6.85z"></path>
        </svg>
      </button>
    </div>

    <!-- Filter bar -->
    {#if filterOpen}
      <div class="filter-bar">
        <button
          type="button"
          class="filter-chip"
          class:selected={filterHasEpub}
          onclick={() => {
            filterHasEpub = !filterHasEpub;
          }}
        >
          has epub
        </button>
        <button
          type="button"
          class="filter-chip"
          class:selected={filterCurrent}
          onclick={() => {
            filterCurrent = !filterCurrent;
          }}
        >
          current
        </button>
        <button
          type="button"
          class="filter-chip"
          class:selected={filterFavorites}
          onclick={() => {
            filterFavorites = !filterFavorites;
          }}
        >
          favorites
        </button>
        <div class="filter-select-wrap">
          <Select
            class="filter-select"
            value={filterCollectionId}
            options={collectionFilterOptions(collections)}
            placeholder="all collections"
            onValueChange={(value) => {
              filterCollectionId = value;
            }}
          />
        </div>
        {#if searchQuery || filterHasEpub || filterFavorites || filterCurrent || filterCollectionId}
          <button
            type="button"
            class="filter-chip"
            onclick={() => {
              searchQuery = "";
              filterHasEpub = false;
              filterFavorites = false;
              filterCurrent = false;
              filterCollectionId = "";
            }}>✕ clear</button
          >
        {/if}
      </div>
    {/if}

    <!-- Results count -->
    {#if !loading && (searchQuery || filterHasEpub || filterFavorites || filterCurrent || filterCollectionId)}
      <div class="results-count">
        {filteredBooks.length} of {books.length} title{books.length !== 1
          ? "s"
          : ""}
      </div>
    {/if}

    <!-- Book list -->
    {#if loading}
      <div class="empty-state">loading...</div>
    {:else if books.length === 0}
      <div class="empty-state">
        no titles tracked yet —
        <button
          type="button"
          class="btn btn-ghost"
          style="display:inline-flex;height:auto;padding:0;text-decoration:underline;text-underline-offset:2px;"
          onclick={() => openDrawer("track")}>add one</button
        >
      </div>
    {:else if filteredBooks.length === 0}
      <div class="empty-state">no titles match filters</div>
    {:else}
      <div class="book-list">
        {#each filteredBooks as book (book.book_id)}
          <article class="book-item">
            <div class="book-cover-shell">
              {#if coverUrl(book)}
                <img
                  class="book-cover"
                  src={coverUrl(book) ?? undefined}
                  alt={`Cover for ${book.title}`}
                  loading="lazy"
                />
              {:else}
                <div class="book-cover book-cover--empty">
                  <span>{book.title.slice(0, 1)}</span>
                </div>
              {/if}
            </div>

            <div class="book-main">
              <div class="book-item-top">
                <div class="book-title-area">
                  <div class="book-name">{book.title}</div>
                  <div class="book-author">{book.author ?? "unknown creator"}</div>
                </div>
              </div>

              <div class="book-meta-row">
                <div class="book-meta-stats">
                  <span class="book-chip">{book.known_remote_chapters} ch</span>
                  {#if book.last_remote_chapter_key}
                    <span class="book-chip">{book.last_remote_chapter_key}</span>
                  {/if}
                  {#if book.latestArtifact}
                    <span class="book-chip"
                      >{formatBytes(book.latestArtifact.file_size_bytes)}</span
                    >
                  {:else if bookSyncLabel(book.book_id)}
                    <span class="book-chip book-chip--live">{bookSyncLabel(book.book_id)}</span>
                  {:else}
                    <span class="book-chip" style="color:var(--text-ghost);"
                      >no epub</span
                    >
                  {/if}
                  <span class="book-dot">·</span>
                  <span class="book-timestamp">checked {formatDate(book.last_checked_at)}</span>
                </div>
                <button
                  type="button"
                  class="book-control-trigger"
                  onclick={() => openBookDrawer(book.book_id)}
                  aria-label={`Open controls for ${book.title}`}
                >
                  <span class="book-control-label">manage</span>
                  <span class="book-control-icon" aria-hidden="true">
                    <DotsThreeOutlineVerticalIcon size={16} weight="bold" />
                  </span>
                </button>
              </div>
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </main>

  <!-- ─── Drawer ─────────────��───────────────── -->
  {#if drawerOpen}
    <div
      class="drawer-backdrop"
      class:closing={drawerClosing}
      role="button"
      tabindex="-1"
      aria-label="Close drawer"
      onclick={closeDrawer}
      onkeydown={(e) => {
        if (e.key === "Escape") closeDrawer();
      }}
    ></div>

    <div class="drawer-shell" class:closing={drawerClosing}>
      <div class="drawer" class:closing={drawerClosing} role="dialog" aria-modal="true">
        <div class="drawer-handle"><div class="drawer-handle-bar"></div></div>

        <div class="drawer-header">
          {#if drawerBook}
            <div class="drawer-title-block">
              <div class="drawer-title">{drawerBook.title}</div>
              <div class="drawer-subtitle">{drawerBook.author ?? "unknown creator"}</div>
            </div>
          {:else}
            <span class="drawer-title">
              {#if drawerTab === "track"}add title
              {:else if drawerTab === "auth"}ranobelib auth
              {:else if drawerTab === "jobs"}recent jobs
              {:else if drawerTab === "library"}library
              {:else}title controls{/if}
            </span>
          {/if}
          <button type="button" class="drawer-close" onclick={closeDrawer}>✕</button>
        </div>

        {#key drawerTab}
          <div class="drawer-panel">
            <!-- Track tab -->
            {#if drawerTab === "track"}
              <div class="drawer-body">
                <div class="form-field">
                  <label for="book-url" class="form-label">ranobelib url</label>
                  <input
                    id="book-url"
                    class="form-input"
                    type="url"
                    placeholder="https://ranobelib.me/ru/book/..."
                    bind:value={bookUrl}
                    oninput={() => clearPreview()}
                  />
                </div>

                <button
                  type="button"
                  class="btn btn-outline"
                  style="width:100%;height:40px;"
                  disabled={previewing || !bookUrl.trim()}
                  onclick={() => void inspectBookUrl()}
                >
                  {previewing ? "loading title..." : "inspect title"}
                </button>

                {#if preview}
                  <div class="preview-card">
                    <div class="preview-cover-shell">
                      {#if preview.cover_url}
                        <img
                          class="preview-cover"
                          src={preview.cover_url}
                          alt={`Cover for ${preview.title}`}
                        />
                      {:else}
                        <div class="preview-cover preview-cover--empty">
                          <span>{preview.title.slice(0, 1)}</span>
                        </div>
                      {/if}
                    </div>
                    <div class="preview-copy">
                      <div class="preview-title">{preview.title}</div>
                      <div class="preview-author">{preview.author ?? "unknown creator"}</div>
                      <div class="preview-meta">{preview.available_chapters} chapters ready</div>
                    </div>
                  </div>

                  <div class="form-field">
                    <label for="branch-select" class="form-label">branch</label>
                    <Select
                      id="branch-select"
                      class="form-select"
                      bind:value={selectedBranchId}
                      options={branchOptions(preview.branches)}
                      placeholder="default branch"
                    />
                  </div>
                {/if}

                <button
                  type="button"
                  class="btn btn-solid"
                  style="width:100%;height:44px;"
                  disabled={submitting || !bookUrl.trim() || !preview}
                  onclick={() => void submitBook()}
                >
                  {submitting ? "queueing..." : "track and build"}
                </button>
              </div>

              <!-- Auth tab -->
            {:else if drawerTab === "auth"}
              <div class="drawer-body">
                <div class="status-row">
                  <div class="status-cell">
                    <div class="status-cell-label">access</div>
                    <div
                      class="status-cell-value"
                      class:active={credential?.has_access_token}
                    >
                      {credential?.has_access_token ? "stored" : "missing"}
                    </div>
                  </div>
                  <div class="status-cell">
                    <div class="status-cell-label">refresh</div>
                    <div
                      class="status-cell-value"
                      class:active={credential?.has_refresh_token}
                    >
                      {credential?.has_refresh_token ? "stored" : "missing"}
                    </div>
                  </div>
                  <div class="status-cell">
                    <div class="status-cell-label">remote</div>
                    <div
                      class="status-cell-value"
                      class:active={validation?.valid}
                      class:error={validation && !validation.valid}
                    >
                      {validation?.valid ? "valid" : validation ? "failed" : "idle"}
                    </div>
                  </div>
                </div>

                {#if validation?.username || validation?.email}
                  <div
                    style="font-size:11px;color:var(--text-muted);padding:0.5rem 0.75rem;border:1px solid var(--line);background:var(--void-3);"
                  >
                    logged in as {validation.username ?? validation.email}
                  </div>
                {/if}

                <div class="form-field">
                  <label for="access-token" class="form-label">access token</label>
                  <textarea
                    id="access-token"
                    class="form-textarea"
                    placeholder="paste bearer token"
                    bind:value={accessToken}
                  ></textarea>
                </div>

                <div class="form-field">
                  <label for="refresh-token" class="form-label">refresh token</label>
                  <textarea
                    id="refresh-token"
                    class="form-textarea"
                    placeholder="paste refresh token"
                    bind:value={refreshToken}
                  ></textarea>
                </div>

                <div style="display:flex;gap:0.5rem;">
                  <button
                    type="button"
                    class="btn btn-outline"
                    style="flex:1;"
                    disabled={validating}
                    onclick={() => void runValidation()}
                  >
                    {validating ? "checking..." : "validate"}
                  </button>
                  <button
                    type="button"
                    class="btn btn-solid"
                    style="flex:1;"
                    disabled={submitting}
                    onclick={() => void saveCredential()}
                  >
                    {submitting ? "saving..." : "save tokens"}
                  </button>
                </div>
              </div>

              <!-- Jobs tab -->
            {:else if drawerTab === "jobs"}
              <div class="drawer-body">
                {#if jobs.length === 0}
                  <div
                    style="padding:2rem 0;text-align:center;color:var(--text-ghost);font-size:12px;"
                  >
                    no jobs yet
                  </div>
                {:else}
                  {#each jobs as job}
                    <div class="job-row">
                      <div>
                        <div class="job-type">{job.type}</div>
                        <div class="job-status {job.status}">{job.status}</div>
                      </div>
                      <div class="job-time">
                        <div
                          style="color:var(--text-ghost);font-size:10px;margin-bottom:1px;"
                        >
                          {job.book_id ? job.book_id.slice(0, 16) + "…" : "global"}
                        </div>
                        {formatDate(job.created_at)}
                      </div>
                    </div>
                  {/each}
                {/if}
              </div>
            {:else if drawerTab === "library"}
              <div class="drawer-body">
                <div class="form-field">
                  <label for="collection-name" class="form-label">new collection</label>
                  <input
                    id="collection-name"
                    class="form-input"
                    type="text"
                    placeholder="favorites, backlog, weekend..."
                    bind:value={collectionName}
                  />
                </div>

                <div class="form-field">
                  <label for="collection-description" class="form-label">description</label>
                  <textarea
                    id="collection-description"
                    class="form-textarea"
                    placeholder="optional note"
                    bind:value={collectionDescription}
                  ></textarea>
                </div>

                <button
                  type="button"
                  class="btn btn-solid"
                  disabled={savingCollection || !collectionName.trim()}
                  onclick={() => void createLibraryCollection()}
                >
                  {savingCollection ? "creating..." : "create collection"}
                </button>

                <div class="drawer-section">
                  <div class="drawer-section-label">collections</div>
                  {#if collections.length === 0}
                    <div class="drawer-empty-copy">no collections yet</div>
                  {:else}
                    <div class="collection-list">
                      {#each collections as collection}
                        <div class="collection-row">
                          <div>
                            <div class="collection-name">{collection.name}</div>
                            <div class="collection-meta">{collection.book_count} title{collection.book_count !== 1 ? "s" : ""}</div>
                          </div>
                          <button
                            type="button"
                            class="btn btn-danger btn-compact"
                            onclick={() => void removeCollection(collection)}
                          >delete</button>
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              </div>
            {:else if drawerBook}
              <div class="drawer-body">
                <div class="form-field">
                  <label for="book-branch-select" class="form-label">branch</label>
                  <Select
                    id="book-branch-select"
                    class="form-select"
                    value={branchSelectValue(drawerBook)}
                    options={branchOptions(drawerBook.branches)}
                    placeholder="default branch"
                    disabled={actionBookId === drawerBook.book_id || drawerBook.branches.length === 0}
                    onValueChange={(value) => void changeBookBranch(drawerBook.book_id, value || null)}
                  />
                </div>

                <div class="toggle-row">
                  <button
                    type="button"
                    class="filter-chip"
                    class:selected={preferenceIsCurrent}
                    onclick={() => {
                      preferenceIsCurrent = !preferenceIsCurrent;
                    }}
                  >
                    current
                  </button>
                  <button
                    type="button"
                    class="filter-chip"
                    class:selected={preferenceIsFavorite}
                    onclick={() => {
                      preferenceIsFavorite = !preferenceIsFavorite;
                    }}
                  >
                    favorite
                  </button>
                </div>

                <div class="form-field">
                  <label for="book-rating" class="form-label">rating</label>
                  <Select
                    id="book-rating"
                    class="form-select"
                    bind:value={preferenceRating}
                    options={ratingOptions}
                    placeholder="no rating"
                  />
                </div>

                <div class="form-field">
                  <label for="book-comment" class="form-label">comment</label>
                  <textarea
                    id="book-comment"
                    class="form-textarea"
                    placeholder="private note"
                    bind:value={preferenceComment}
                  ></textarea>
                </div>

                <div class="drawer-section">
                  <div class="drawer-section-label">collections</div>
                  <div class="chip-grid">
                    {#each collections as collection}
                      <button
                        type="button"
                        class="filter-chip"
                        class:selected={preferenceCollectionIds.includes(collection.id)}
                        onclick={() => toggleCollectionValue(collection.id)}
                      >
                        {collection.name}
                      </button>
                    {/each}
                  </div>
                </div>

                <div class="drawer-section">
                  <div class="drawer-section-label">visible genres in opds</div>
                  <div class="chip-grid">
                    {#each drawerBook.genres as genre}
                      <button
                        type="button"
                        class="filter-chip"
                        class:selected={preferenceVisibleGenres.includes(genre.slug)}
                        onclick={() => toggleNamedValue("genre", genre)}
                      >
                        {genre.name}
                      </button>
                    {/each}
                  </div>
                </div>

                <div class="drawer-section">
                  <div class="drawer-section-label">visible tags in opds</div>
                  <div class="chip-grid">
                    {#each drawerBook.tags as tag}
                      <button
                        type="button"
                        class="filter-chip"
                        class:selected={preferenceVisibleTags.includes(tag.slug)}
                        onclick={() => toggleNamedValue("tag", tag)}
                      >
                        {tag.name}
                      </button>
                    {/each}
                  </div>
                </div>

                <div class="book-drawer-actions">
                  <button
                    type="button"
                    class="btn btn-solid"
                    disabled={savingPreferences}
                    onclick={() => void saveBookPreferences()}
                    >save</button
                  >
                  <button
                    type="button"
                    class="btn btn-outline"
                    disabled={actionBookId === drawerBook.book_id}
                    onclick={() => void runBookAction(drawerBook.book_id)}
                    >check now</button
                  >
                  {#if artifactUrl(drawerBook)}
                    <a href={artifactUrl(drawerBook)} class="btn btn-ghost">download epub</a>
                  {/if}
                  <button
                    type="button"
                    class="btn btn-danger"
                    disabled={actionBookId === drawerBook.book_id}
                    onclick={() => void removeBook(drawerBook)}
                    >delete</button
                  >
                </div>
              </div>
            {/if}
          </div>
        {/key}
      </div>
    </div>
  {/if}

  <!-- ���── Floating action group ───────────────── -->
  <div class="fab-group">
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("jobs")}
      title="Recent jobs"
      aria-label="Recent jobs">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M5 12h14M5 17h14"></path></svg>
    </button
    >
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("library")}
      title="Library"
      aria-label="Library">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h12v14H6zM9 9h6M9 13h6"></path></svg>
    </button
    >
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("auth")}
      title="Auth settings"
      aria-label="Auth settings">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l6 3v5c0 4.2-2.6 7.7-6 9-3.4-1.3-6-4.8-6-9V6zM12 10v4M12 7h.01"></path></svg>
    </button
    >
    <button
      type="button"
      class="fab fab-primary"
      onclick={() => openDrawer("track")}
      title="Add title"
      aria-label="Add a title">+</button
    >
  </div>

  <ToastContainer />
</div>
