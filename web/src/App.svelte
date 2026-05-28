<script lang="ts">
  import { onMount } from "svelte";
  import ToastContainer from "./lib/components/ToastContainer.svelte";
  import { toast } from "./lib/components/toast-store.svelte";
  import {
    createTrackedBook,
    getCredential,
    latestArtifact,
    listJobs,
    listTrackedBooks,
    putCredential,
    triggerBuild,
    triggerCheck,
    validateCredential,
    type ArtifactSummary,
    type CredentialValidation,
    type CredentialView,
    type JobSummary,
    type TrackedBook,
  } from "./lib/api";

  type BookCard = TrackedBook & { latestArtifact: ArtifactSummary | null };

  // ─── State ───────────────────────────���────────────────
  let books = $state<BookCard[]>([]);
  let jobs = $state<JobSummary[]>([]);
  let credential = $state<CredentialView | null>(null);
  let validation = $state<CredentialValidation | null>(null);

  let loading = $state(true);
  let submitting = $state(false);
  let validating = $state(false);
  let actionBookId = $state<string | null>(null);

  // Form fields
  let accessToken = $state("");
  let refreshToken = $state("");
  let bookUrl = $state("");
  let branchMode = $state("default");

  // UI state
  let drawerOpen = $state(false);
  let drawerTab = $state<"track" | "auth" | "jobs">("track");
  let searchQuery = $state("");
  let sortMode = $state<"title" | "checked" | "chapters">("title");
  let sortAsc = $state(true);
  let filterOpen = $state(false);
  let filterHasEpub = $state(false);

  // ─── Derived ─────���───────────────────�─────────────────
  const runningJobs = $derived(
    jobs.filter((j) => j.status === "running").length,
  );
  const failedJobs = $derived(jobs.filter((j) => j.status === "failed").length);

  const filteredBooks = $derived.by(() => {
    let result = books.slice();

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (b) =>
          b.title.toLowerCase().includes(q) || b.slug.toLowerCase().includes(q),
      );
    }

    if (filterHasEpub) {
      result = result.filter((b) => b.latestArtifact !== null);
    }

    result.sort((a, b) => {
      let cmp = 0;
      if (sortMode === "title") {
        cmp = a.title.localeCompare(b.title);
      } else if (sortMode === "checked") {
        const da = a.last_checked_at
          ? new Date(a.last_checked_at).getTime()
          : 0;
        const db = b.last_checked_at
          ? new Date(b.last_checked_at).getTime()
          : 0;
        cmp = db - da;
      } else if (sortMode === "chapters") {
        cmp = b.known_remote_chapters - a.known_remote_chapters;
      }
      return sortAsc ? cmp : -cmp;
    });

    return result;
  });

  // ─── Data loading ───────────────────���──────────────────
  async function loadDashboard() {
    loading = true;
    try {
      credential = await getCredential();
      const [trackedBooks, recentJobs] = await Promise.all([
        listTrackedBooks(),
        listJobs(),
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

  async function submitBook() {
    submitting = true;
    try {
      await createTrackedBook({
        url: bookUrl.trim(),
        branch_mode: branchMode,
        selected_branch_id: null,
      });
      bookUrl = "";
      drawerOpen = false;
      toast.success("tracked title added");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to track title",
      );
    } finally {
      submitting = false;
    }
  }

  async function runBookAction(bookId: string, action: "check" | "build") {
    actionBookId = bookId;
    try {
      if (action === "check") {
        await triggerCheck(bookId);
        toast.success("queued update check");
      } else {
        await triggerBuild(bookId);
        toast.success("queued epub rebuild");
      }
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : `failed to ${action} title`,
      );
    } finally {
      actionBookId = null;
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

  function cycleSort(mode: typeof sortMode) {
    if (sortMode === mode) {
      sortAsc = !sortAsc;
    } else {
      sortMode = mode;
      sortAsc = true;
    }
  }

  function openDrawer(tab: typeof drawerTab) {
    drawerTab = tab;
    drawerOpen = true;
  }

  onMount(loadDashboard);
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
  <div class="grid-overlay"></div>

  <!-- ─── Header ─────────────────────────────── -->
  <header class="app-header">
    <div class="app-logo">
      <span class="app-logo-name">ranobarr</span>
      <span class="app-logo-sub">/ ranobe tracker</span>
    </div>

    <div class="header-stats">
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
        onclick={() => cycleSort("title")}
        title="Sort by title"
      >
        {#if sortMode === "title"}
          {sortAsc ? "a→z" : "z→a"}
        {:else}
          a–z
        {/if}
      </button>

      <button
        type="button"
        class="sort-btn"
        onclick={() => cycleSort("checked")}
        title="Sort by last checked"
      >
        {#if sortMode === "checked"}
          {sortAsc ? "↑ recent" : "↓ old"}
        {:else}
          date
        {/if}
      </button>

      <button
        type="button"
        class="filter-btn"
        class:active={filterOpen}
        onclick={() => {
          filterOpen = !filterOpen;
        }}
        title="Filters"
        aria-label="Toggle filters">��</button
      >
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
          class:selected={sortMode === "chapters"}
          onclick={() => cycleSort("chapters")}
        >
          most chapters
        </button>
        {#if searchQuery || filterHasEpub}
          <button
            type="button"
            class="filter-chip"
            onclick={() => {
              searchQuery = "";
              filterHasEpub = false;
            }}>✕ clear</button
          >
        {/if}
      </div>
    {/if}

    <!-- Results count -->
    {#if !loading && (searchQuery || filterHasEpub)}
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
            <!-- Top row: title + branch badge -->
            <div class="book-item-top">
              <div class="book-title-area">
                <div class="book-slug">{book.slug}</div>
                <div class="book-name">{book.title}</div>
              </div>
              <span class="book-badge">{book.branch_mode}</span>
            </div>

            <!-- Chips row -->
            <div class="book-meta-row">
              <span class="book-chip">{book.known_remote_chapters} ch</span>
              {#if book.last_remote_chapter_key}
                <span class="book-chip">{book.last_remote_chapter_key}</span>
              {/if}
              {#if book.latestArtifact}
                <span class="book-chip"
                  >{formatBytes(book.latestArtifact.file_size_bytes)}</span
                >
              {:else}
                <span class="book-chip" style="color:var(--text-ghost);"
                  >no epub</span
                >
              {/if}
              <span class="book-dot">·</span>
              <span style="font-size:10px;color:var(--text-ghost);"
                >checked {formatDate(book.last_checked_at)}</span
              >
            </div>

            <!-- Actions -->
            <div class="book-actions">
              <button
                type="button"
                class="btn btn-outline"
                disabled={actionBookId === book.book_id}
                onclick={() => runBookAction(book.book_id, "check")}
                >check</button
              >
              <button
                type="button"
                class="btn btn-solid"
                disabled={actionBookId === book.book_id}
                onclick={() => runBookAction(book.book_id, "build")}
                >build epub</button
              >
              {#if artifactUrl(book)}
                <a
                  href={artifactUrl(book)}
                  class="btn btn-ghost"
                  aria-disabled={false}>↓ epub</a
                >
              {/if}
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
      role="button"
      tabindex="-1"
      aria-label="Close drawer"
      onclick={() => {
        drawerOpen = false;
      }}
      onkeydown={(e) => {
        if (e.key === "Escape") drawerOpen = false;
      }}
    ></div>

    <div class="drawer" role="dialog" aria-modal="true">
      <div class="drawer-handle"><div class="drawer-handle-bar"></div></div>

      <div class="drawer-header">
        <span class="drawer-title">
          {#if drawerTab === "track"}add title
          {:else if drawerTab === "auth"}ranobelib auth
          {:else}recent jobs{/if}
        </span>
        <button
          type="button"
          class="drawer-close"
          onclick={() => {
            drawerOpen = false;
          }}>✕</button
        >
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
                />
              </div>

              <div class="form-field">
                <label for="branch-mode" class="form-label">branch strategy</label>
                <select
                  id="branch-mode"
                  class="form-select form-input"
                  bind:value={branchMode}
                >
                  <option value="default">default branch</option>
                  <option value="selected">selected branch later</option>
                </select>
              </div>

              <button
                type="button"
                class="btn btn-solid"
                style="width:100%;height:44px;"
                disabled={submitting || !bookUrl.trim()}
                onclick={() => void submitBook()}
              >
                {submitting ? "tracking..." : "track title"}
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
          {:else}
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
          {/if}
        </div>
      {/key}
    </div>
  {/if}

  <!-- ���── Floating action group ───────────────── -->
  <div class="fab-group">
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("jobs")}
      title="Recent jobs"
      aria-label="Recent jobs">≡</button
    >
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("auth")}
      title="Auth settings"
      aria-label="Auth settings">⚿</button
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
