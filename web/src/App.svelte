<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import {
    ArrowsClockwiseIcon,
    BooksIcon,
    ClockCounterClockwiseIcon,
    EyeIcon,
    EyeSlashIcon,
    FunnelSimpleIcon,
    HeartStraightIcon,
    PlusIcon,
    ShieldCheckIcon,
  } from "phosphor-svelte";
  import ConfirmDialog from "./lib/components/ConfirmDialog.svelte";
  import Select from "./lib/components/Select.svelte";
  import StarPicker from "./lib/components/StarPicker.svelte";
  import StarRating from "./lib/components/StarRating.svelte";
  import type { SelectOption } from "./lib/components/Select.types";
  import StarField from "./lib/components/StarField.svelte";
  import ToastContainer from "./lib/components/ToastContainer.svelte";
  import { toast } from "./lib/components/toast-store.svelte";
  import {
    createCollection,
    createTrackedBook,
    deleteCollection,
    deleteTrackedBook,
    getBrowserAuthSession,
    getCredential,
    getKOReaderState,
    getOpdsVisibility,
    loginBrowserSession,
    logoutBrowserSession,
    latestArtifact,
    listCollections,
    listJobs,
    listTrackedBooks,
    previewTrackedBook,
    putCredential,
    putOpdsVisibility,
    triggerCheck,
    updateBookPreferences,
    updateKOReaderDocument,
    updateTrackedBookBranch,
    validateCredential,
    ApiError,
    type ArtifactSummary,
    type BrowserAuthSession,
    type BranchSummary,
    type CollectionSummary,
    type CredentialValidation,
    type CredentialView,
    type JobSummary,
    type KOReaderDocument,
    type KOReaderState,
    type NamedTagSummary,
    type OpdsVisibility,
    type PreviewBook,
    type TrackedBook,
  } from "./lib/api";

  type BookCard = TrackedBook & { latestArtifact: ArtifactSummary | null };
  type ManualKOReaderEntry = {
    kind: "koreader";
    id: string;
    title: string;
    author: string | null;
    created_at: string;
    updated_at: string;
    document: KOReaderDocument;
  };
  type TrackedLibraryEntry = {
    kind: "tracked";
    id: string;
    title: string;
    author: string | null;
    created_at: string;
    updated_at: string;
    book: BookCard;
  };
  type LibraryEntry = ManualKOReaderEntry | TrackedLibraryEntry;
  type DrawerTab =
    | "track"
    | "auth"
    | "jobs"
    | "library"
    | "metadata"
    | "device"
    | "book"
    | "koreader-document";

  let books = $state<BookCard[]>([]);
  let jobs = $state<JobSummary[]>([]);
  let collections = $state<CollectionSummary[]>([]);
  let opdsVisibility = $state<OpdsVisibility | null>(null);
  let koreaderState = $state<KOReaderState | null>(null);
  let credential = $state<CredentialView | null>(null);
  let validation = $state<CredentialValidation | null>(null);
  let authSession = $state<BrowserAuthSession | null>(null);

  let loading = $state(true);
  let submitting = $state(false);
  let validating = $state(false);
  let previewing = $state(false);
  let actionBookId = $state<string | null>(null);
  let savingPreferences = $state(false);
  let savingCollection = $state(false);
  let savingOpdsVisibility = $state(false);
  let savingKoreaderDocument = $state(false);

  let accessToken = $state("");
  let refreshToken = $state("");
  let authUsername = $state("");
  let authPassword = $state("");
  let authRememberMe = $state(true);
  let authShowPassword = $state(false);
  let authChecking = $state(true);
  let authSubmitting = $state(false);
  let authError = $state<string | null>(null);
  let bookUrl = $state("");
  let selectedBranchId = $state("");
  let preview = $state<PreviewBook | null>(null);
  let collectionName = $state("");

  let drawerOpen = $state(false);
  let drawerClosing = $state(false);
  let drawerTab = $state<DrawerTab>("track");
  let drawerBookId = $state<string | null>(null);
  let drawerKOReaderDocumentId = $state<string | null>(null);
  let searchQuery = $state("");
  let sortMode = $state<"title" | "updated" | "added">("title");
  let filterOpen = $state(false);
  let filterFavorites = $state(false);
  let filterCollectionId = $state("");
  let drawerCloseTimer: ReturnType<typeof setTimeout> | null = null;
  let preferenceCollectionIds = $state<string[]>([]);
  let preferenceIsFavorite = $state(false);
  let preferenceRating = $state("");
  let preferenceComment = $state("");
  let preferenceTitle = $state("");
  let preferenceAuthor = $state("");
  let pendingVisibleGenreSlugs = $state<string[]>([]);
  let pendingVisibleTagSlugs = $state<string[]>([]);
  let collectionDeleteCandidate = $state<CollectionSummary | null>(null);
  let selectedKOReaderDocumentId = $state<string | null>(null);
  let koreaderDocumentTitle = $state("");
  let koreaderDocumentAuthor = $state("");
  let koreaderLinkedBookId = $state("");

  const runningJobs = $derived(
    jobs.filter((job) => job.status === "running").length,
  );
  const failedJobs = $derived(
    jobs.filter((job) => job.status === "failed").length,
  );
  const favoriteCount = $derived(
    books.filter((book) => book.is_favorite).length,
  );
  const manualKOReaderDocuments = $derived(
    (koreaderState?.documents ?? []).filter((item) => !item.linked_book_id),
  );
  const linkedDeviceProgressByBook = $derived.by(() => {
    const values = new Map<string, number>();
    for (const item of koreaderState?.documents ?? []) {
      if (!item.linked_book_id || item.progress_percent === null) continue;
      const current = values.get(item.linked_book_id);
      if (current === undefined || item.progress_percent > current) {
        values.set(item.linked_book_id, item.progress_percent);
      }
    }
    return values;
  });
  const selectedKOReaderDocument = $derived(
    selectedKOReaderDocumentId
      ? (koreaderState?.documents.find(
          (item) => item.id === selectedKOReaderDocumentId,
        ) ?? null)
      : null,
  );
  const drawerBook = $derived(
    drawerBookId
      ? (books.find((book) => book.book_id === drawerBookId) ?? null)
      : null,
  );
  const drawerKOReaderDocument = $derived(
    drawerKOReaderDocumentId
      ? (koreaderState?.documents.find(
          (item) => item.id === drawerKOReaderDocumentId,
        ) ?? null)
      : null,
  );
  const activeKOReaderDocument = $derived(
    drawerKOReaderDocument ?? selectedKOReaderDocument,
  );
  const syncStateByBook = $derived.by(() => {
    const states = new Map<string, "running" | "queued">();
    for (const job of jobs) {
      if (!job.book_id) continue;
      if (job.type !== "check_updates" && job.type !== "build_artifact")
        continue;
      if (job.status !== "running" && job.status !== "queued") continue;
      if (!states.has(job.book_id)) {
        states.set(
          job.book_id,
          job.status === "running" ? "running" : "queued",
        );
      }
    }
    return states;
  });
  const currentSyncedBookId = $derived.by(() => {
    const recent = (koreaderState?.documents ?? [])
      .filter((document) => document.linked_book_id && document.progress_timestamp !== null)
      .sort((left, right) => (right.progress_timestamp ?? 0) - (left.progress_timestamp ?? 0));
    return recent[0]?.linked_book_id ?? null;
  });
  const totalTitleCount = $derived(
    books.length + manualKOReaderDocuments.length,
  );
  const showBrowserAuth = $derived(
    authChecking || (authSession?.auth_enabled === true && !authSession.authenticated),
  );
  const filteredLibraryEntries = $derived.by(() => {
    let result: LibraryEntry[] = [
      ...books.map((book) => ({
        kind: "tracked" as const,
        id: book.book_id,
        title: book.title,
        author: book.author,
        created_at: book.created_at,
        updated_at: book.updated_at,
        book,
      })),
      ...manualKOReaderDocuments.map((document) => ({
        kind: "koreader" as const,
        id: document.id,
        title:
          document.title ??
          document.linked_book_title ??
          `document ${document.document_hash.slice(0, 8)}`,
        author: document.author,
        created_at: document.created_at,
        updated_at: document.updated_at,
        document,
      })),
    ];
    const query = searchQuery.trim().toLowerCase();
    if (query) {
      result = result.filter(
        (entry) =>
          entry.title.toLowerCase().includes(query) ||
          (entry.author ?? "").toLowerCase().includes(query),
      );
    }
    if (filterFavorites) {
      result = result.filter(
        (entry) => entry.kind === "tracked" && entry.book.is_favorite,
      );
    }
    if (filterCollectionId) {
      result = result.filter(
        (entry) =>
          entry.kind === "tracked" &&
          entry.book.collections.some(
            (collection) => collection.id === filterCollectionId,
          ),
      );
    }
    result.sort((left, right) => {
      if (sortMode === "updated") {
        return (
          new Date(right.updated_at).getTime() -
          new Date(left.updated_at).getTime()
        );
      }
      if (sortMode === "added") {
        return (
          new Date(right.created_at).getTime() -
          new Date(left.created_at).getTime()
        );
      }
      return left.title.localeCompare(right.title);
    });
    return result;
  });

  async function loadDashboard() {
    loading = true;
    try {
      const [
        storedCredential,
        recentJobs,
        trackedBooks,
        libraryCollections,
        visibility,
        deviceState,
      ] = await Promise.all([
        getCredential(),
        listJobs(),
        listTrackedBooks("title"),
        listCollections(),
        getOpdsVisibility(),
        getKOReaderState(),
      ]);
      credential = storedCredential;
      accessToken = "";
      refreshToken = "";
      const artifactPairs = await Promise.all(
        trackedBooks.map(async (book) => ({
          bookId: book.book_id,
          artifact: await latestArtifact(book.book_id),
        })),
      );
      const artifactMap = new Map(
        artifactPairs.map((entry) => [entry.bookId, entry.artifact]),
      );
      books = trackedBooks.map((book) => ({
        ...book,
        latestArtifact: artifactMap.get(book.book_id) ?? null,
      }));
      jobs = recentJobs.slice(0, 20);
      collections = libraryCollections;
      opdsVisibility = visibility;
      koreaderState = deviceState;
      pendingVisibleGenreSlugs = [...visibility.visible_genre_slugs];
      pendingVisibleTagSlugs = [...visibility.visible_tag_slugs];
      authError = null;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        authSession = { auth_enabled: true, authenticated: false, username: null };
        return;
      }
      toast.error(error instanceof Error ? error.message : "failed to load dashboard");
    } finally {
      loading = false;
    }
  }

  async function loadAuthSession() {
    authChecking = true;
    try {
      authSession = await getBrowserAuthSession();
      if (!authSession.auth_enabled || authSession.authenticated) {
        await loadDashboard();
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "failed to check auth");
    } finally {
      authChecking = false;
    }
  }

  async function submitBrowserAuth() {
    if (!authUsername.trim() || !authPassword) return;
    authSubmitting = true;
    authError = null;
    try {
      authSession = await loginBrowserSession({
        username: authUsername.trim(),
        password: authPassword,
        remember_me: authRememberMe,
      });
      authPassword = "";
      await loadDashboard();
    } catch (error) {
      authError = error instanceof Error ? error.message : "failed to sign in";
    } finally {
      authSubmitting = false;
    }
  }

  async function signOutBrowserSession() {
    try {
      authSession = await logoutBrowserSession();
      authPassword = "";
      closeDrawer();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "failed to sign out");
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
        title: preferenceTitle.trim() || null,
        author: preferenceAuthor.trim() || null,
        is_favorite: preferenceIsFavorite,
        rating: preferenceRating ? Number(preferenceRating) : null,
        comment: preferenceComment.trim() || null,
        collection_ids: preferenceCollectionIds,
      });
      toast.success("saved title preferences");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "failed to save title preferences",
      );
    } finally {
      savingPreferences = false;
    }
  }

  async function createLibraryCollection() {
    if (!collectionName.trim()) return;
    savingCollection = true;
    try {
      await createCollection({ name: collectionName.trim() });
      collectionName = "";
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

  async function confirmRemoveCollection() {
    if (!collectionDeleteCandidate) return;
    try {
      await deleteCollection(collectionDeleteCandidate.id);
      collectionDeleteCandidate = null;
      toast.success("collection removed");
      await loadDashboard();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to delete collection",
      );
    }
  }

  async function saveOpdsVisibility() {
    savingOpdsVisibility = true;
    try {
      opdsVisibility = await putOpdsVisibility({
        visible_genre_slugs: pendingVisibleGenreSlugs,
        visible_tag_slugs: pendingVisibleTagSlugs,
      });
      toast.success("saved opds metadata visibility");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "failed to save opds visibility",
      );
    } finally {
      savingOpdsVisibility = false;
    }
  }

  async function saveKOReaderDocument() {
    if (!activeKOReaderDocument) return;
    savingKoreaderDocument = true;
    try {
      koreaderState = await updateKOReaderDocument(activeKOReaderDocument.id, {
        title: koreaderDocumentTitle.trim() || null,
        author: koreaderDocumentAuthor.trim() || null,
        linked_book_id: koreaderLinkedBookId || null,
      });
      toast.success("saved synced title metadata");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "failed to save synced title",
      );
    } finally {
      savingKoreaderDocument = false;
    }
  }

  function artifactUrl(book: BookCard): string | null {
    return book.latestArtifact
      ? `/api/v1/artifacts/${book.latestArtifact.id}/download`
      : null;
  }

  function coverUrl(
    book: Pick<BookCard, "book_id" | "cover_url">,
  ): string | null {
    return book.cover_url ? `/opds/books/${book.book_id}/cover` : null;
  }

  function formatDate(value: string | null): string {
    if (!value) return "never";
    const date = new Date(value);
    const now = new Date();
    const diffMin = Math.floor((now.getTime() - date.getTime()) / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  }

  function formatBytes(value: number): string {
    if (value < 1024) return `${value} b`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} kb`;
    return `${(value / (1024 * 1024)).toFixed(1)} mb`;
  }

  function formatPercent(value: number | null): string {
    if (value === null) return "no progress";
    return `${Math.round(value)}%`;
  }

  function formatTimestamp(value: number | null): string {
    if (value === null) return "never";
    return formatDate(new Date(value * 1000).toISOString());
  }

  function openDrawer(tab: DrawerTab) {
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

  function openKOReaderDocumentDrawer(documentId: string) {
    drawerKOReaderDocumentId = documentId;
    selectedKOReaderDocumentId = documentId;
    openDrawer("koreader-document");
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
      if (drawerTab === "koreader-document") {
        drawerKOReaderDocumentId = null;
      }
      drawerCloseTimer = null;
    }, 300);
  }

  function branchOptions(branches: BranchSummary[]): SelectOption[] {
    return [
      { value: "", label: "default branch" },
      ...branches.map((branch) => ({
        value: branch.id,
        label: branch.display,
      })),
    ];
  }

  function collectionFilterOptions(items: CollectionSummary[]): SelectOption[] {
    return [
      { value: "", label: "all collections" },
      ...items.map((item) => ({ value: item.id, label: item.name })),
    ];
  }

  function branchSelectValue(
    book: Pick<BookCard, "selected_branch_id">,
  ): string {
    return book.selected_branch_id ?? "";
  }

  function koreaderLinkOptions(items: BookCard[]): SelectOption[] {
    return [
      { value: "", label: "unlinked" },
      ...items.map((item) => ({ value: item.book_id, label: item.title })),
    ];
  }

  function bookSyncLabel(bookId: string): string | null {
    const state = syncStateByBook.get(bookId);
    if (!state) return null;
    return state === "running" ? "syncing" : "queued";
  }

  function setSort(mode: typeof sortMode) {
    sortMode = mode;
  }

  function toggleSlugValue(values: string[], slug: string) {
    return values.includes(slug)
      ? values.filter((value) => value !== slug)
      : [...values, slug];
  }

  function toggleNamedValue(kind: "genre" | "tag", item: NamedTagSummary) {
    if (kind === "genre") {
      pendingVisibleGenreSlugs = toggleSlugValue(
        pendingVisibleGenreSlugs,
        item.slug,
      );
      return;
    }
    pendingVisibleTagSlugs = toggleSlugValue(pendingVisibleTagSlugs, item.slug);
  }

  function toggleCollectionValue(collectionId: string) {
    preferenceCollectionIds = toggleSlugValue(
      preferenceCollectionIds,
      collectionId,
    );
  }

  function syncDrawerBookPreferences(book: BookCard | null) {
    if (!book) return;
    preferenceTitle = book.title;
    preferenceAuthor = book.author ?? "";
    preferenceCollectionIds = book.collections.map(
      (collection) => collection.id,
    );
    preferenceIsFavorite = book.is_favorite;
    preferenceRating = book.rating ? String(book.rating) : "";
    preferenceComment = book.comment ?? "";
  }

  function syncKOReaderDocumentForm(document: KOReaderDocument | null) {
    if (!document) return;
    koreaderDocumentTitle = document.title ?? "";
    koreaderDocumentAuthor = document.author ?? "";
    koreaderLinkedBookId = document.linked_book_id ?? "";
  }

  function jobTypeLabel(type: string): string {
    if (type === "check_updates") return "check";
    if (type === "build_artifact") return "build";
    return type;
  }

  function jobTriggerLabel(trigger: string | null): string {
    if (trigger === "import") return "import";
    if (trigger === "manual") return "manual";
    if (trigger === "automatic") return "automatic";
    return "system";
  }

  function handleWindowKeydown(event: KeyboardEvent) {
    if (event.key === "Escape" && drawerOpen) {
      event.preventDefault();
      closeDrawer();
    }
  }

  onMount(() => {
    window.addEventListener("keydown", handleWindowKeydown);
    void loadAuthSession();
    return () => {
      window.removeEventListener("keydown", handleWindowKeydown);
    };
  });
  $effect(() => {
    syncDrawerBookPreferences(drawerBook);
  });
  $effect(() => {
    syncKOReaderDocumentForm(activeKOReaderDocument);
  });
  onDestroy(() => {
    if (drawerCloseTimer) clearTimeout(drawerCloseTimer);
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

{#if showBrowserAuth}
  <main class="auth-shell">
    <StarField count={54} />
    <div class="grid-overlay"></div>

    <div class="auth-card-shell">
      {#if authChecking}
        <div class="auth-loading-copy">checking session...</div>
      {:else}
        <div class="auth-brand">
          <div class="auth-brand-name">ranobarr</div>
          <div class="auth-brand-copy">sign in to open your library</div>
        </div>

        <div class="auth-card">
          <form
            class="auth-form"
            onsubmit={(event) => {
              event.preventDefault();
              void submitBrowserAuth();
            }}
          >
            <div class="form-field">
              <label for="browser-auth-username" class="form-label">username</label>
              <input
                id="browser-auth-username"
                class="form-input"
                type="text"
                autocomplete="username"
                bind:value={authUsername}
              />
            </div>

            <div class="form-field auth-password-field">
              <label for="browser-auth-password" class="form-label">password</label>
              <input
                id="browser-auth-password"
                class="form-input auth-password-input"
                type={authShowPassword ? "text" : "password"}
                autocomplete="current-password"
                bind:value={authPassword}
              />
              <button
                type="button"
                class="auth-password-toggle"
                aria-label={authShowPassword ? "Hide password" : "Show password"}
                onclick={() => {
                  authShowPassword = !authShowPassword;
                }}
              >
                {#if authShowPassword}
                  <EyeSlashIcon size={16} />
                {:else}
                  <EyeIcon size={16} />
                {/if}
              </button>
            </div>

            <label class="auth-remember-row">
              <input type="checkbox" bind:checked={authRememberMe} />
              <span>remember this browser</span>
            </label>

            {#if authError}
              <div class="auth-error">{authError}</div>
            {/if}

            <button
              type="submit"
              class="btn btn-solid full-width-btn"
              disabled={authSubmitting || !authUsername.trim() || !authPassword}
            >
              {authSubmitting ? "signing in..." : "sign in"}
            </button>
          </form>
        </div>
      {/if}
    </div>
  </main>
{:else}
<div class="page-shell">
  <StarField count={54} />
  <div class="grid-overlay"></div>

  <header class="app-header">
    <div class="app-logo">
      <span class="app-logo-name">ranobarr</span>
      <span class="app-logo-sub">/ ranobe tracker</span>
    </div>

    <div class="header-stats">
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
        <span class="stat-pill-value">{totalTitleCount}</span>
        <span>titles</span>
      </div>
    </div>
  </header>

  <main class="page-body">
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
      <div class="toolbar-actions">
        <button
          type="button"
          class="sort-btn"
          class:active={sortMode === "title"}
          onclick={() => setSort("title")}
        >
          title
        </button>
        <button
          type="button"
          class="sort-btn"
          class:active={sortMode === "updated"}
          onclick={() => setSort("updated")}
        >
          updated
        </button>
        <button
          type="button"
          class="sort-btn"
          class:active={sortMode === "added"}
          onclick={() => setSort("added")}
        >
          added
        </button>
        <button
          type="button"
          class="filter-btn"
          class:active={filterOpen}
          onclick={() => {
            filterOpen = !filterOpen;
          }}
          aria-label="Toggle filters"
        >
          <FunnelSimpleIcon size={14} weight="bold" />
        </button>
      </div>
    </div>

    {#if filterOpen}
      <div class="filter-bar">
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
        {#if searchQuery || filterFavorites || filterCollectionId}
          <button
            type="button"
            class="filter-chip"
            onclick={() => {
              searchQuery = "";
              filterFavorites = false;
              filterCollectionId = "";
            }}
          >
            ✕ clear
          </button>
        {/if}
      </div>
    {/if}

    {#if !loading && (searchQuery || filterFavorites || filterCollectionId)}
      <div class="results-count">
        {filteredLibraryEntries.length} of {totalTitleCount} title{totalTitleCount !==
        1
          ? "s"
          : ""}
      </div>
    {/if}

    {#if loading}
      <div class="empty-state">loading...</div>
    {:else if totalTitleCount === 0}
      <div class="empty-state">
        no titles tracked yet —
        <button
          type="button"
          class="btn btn-ghost inline-link-button"
          onclick={() => openDrawer("track")}
        >
          add one
        </button>
      </div>
    {:else if filteredLibraryEntries.length === 0}
      <div class="empty-state">no titles match filters</div>
    {:else}
      <div class="book-list">
        {#each filteredLibraryEntries as entry (`${entry.kind}:${entry.id}`)}
          {#if entry.kind === "tracked"}
            <div
              class="book-item"
              class:book-item--current={currentSyncedBookId ===
                entry.book.book_id}
              role="button"
              tabindex="0"
              onclick={() => openBookDrawer(entry.book.book_id)}
              onkeydown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openBookDrawer(entry.book.book_id);
                }
              }}
            >
              <div class="book-cover-shell">
                {#if coverUrl(entry.book)}
                  <img
                    class="book-cover"
                    src={coverUrl(entry.book) ?? undefined}
                    alt={`Cover for ${entry.book.title}`}
                    loading="lazy"
                  />
                {:else}
                  <div class="book-cover book-cover--empty">
                    <span>{entry.book.title.slice(0, 1)}</span>
                  </div>
                {/if}
              </div>

              <div class="book-main">
                <div class="book-title-area">
                  <div class="book-name">{entry.book.title}</div>
                  <div class="book-author">
                    {entry.book.author ?? "unknown creator"}
                  </div>
                </div>

                <div class="book-meta-row">
                  <div class="book-meta-stats">
                    {#if entry.book.is_favorite}
                      <span class="book-favorite" aria-label="Favorite">
                        <HeartStraightIcon size={12} weight="fill" />
                      </span>
                    {/if}
                    {#if entry.book.rating}
                      <StarRating value={entry.book.rating} size={11} />
                    {/if}
                    <span class="book-chip"
                      >{entry.book.known_remote_chapters} ch</span
                    >
                    {#if entry.book.last_remote_chapter_key}
                      <span class="book-chip"
                        >{entry.book.last_remote_chapter_key}</span
                      >
                    {/if}
                    {#if linkedDeviceProgressByBook.has(entry.book.book_id)}
                      <span class="book-chip book-chip--live"
                        >{formatPercent(
                          linkedDeviceProgressByBook.get(entry.book.book_id) ??
                            null,
                        )} read</span
                      >
                    {/if}
                    {#if entry.book.latestArtifact}
                      <span class="book-chip"
                        >{formatBytes(
                          entry.book.latestArtifact.file_size_bytes,
                        )}</span
                      >
                    {:else if bookSyncLabel(entry.book.book_id)}
                      <span class="book-chip book-chip--live"
                        >{bookSyncLabel(entry.book.book_id)}</span
                      >
                    {:else}
                      <span class="book-chip book-chip-muted">no epub</span>
                    {/if}
                    <span class="book-dot">·</span>
                    <span class="book-timestamp"
                      >updated {formatDate(entry.book.updated_at)}</span
                    >
                  </div>
                </div>
              </div>
            </div>
          {:else}
            <div
              class="book-item book-item--device"
              role="button"
              tabindex="0"
              onclick={() => openKOReaderDocumentDrawer(entry.document.id)}
              onkeydown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openKOReaderDocumentDrawer(entry.document.id);
                }
              }}
            >
              <div class="book-cover-shell">
                <div class="book-cover book-cover--empty book-cover--device">
                  <span>KO</span>
                </div>
              </div>

              <div class="book-main">
                <div class="book-title-area">
                  <div class="book-name">{entry.title}</div>
                  <div class="book-author">
                    {entry.author ?? "manual device title"}
                  </div>
                </div>

                <div class="book-meta-row">
                  <div class="book-meta-stats">
                    <span class="book-chip book-chip--device"
                      >{entry.document.device ?? "device"}</span
                    >
                    <span class="book-chip book-chip--live"
                      >{formatPercent(entry.document.progress_percent)} read</span
                    >
                    <span class="book-chip">{entry.document.username}</span>
                    <span class="book-dot">·</span>
                    <span class="book-timestamp"
                      >synced {formatTimestamp(
                        entry.document.progress_timestamp,
                      )}</span
                    >
                  </div>
                </div>
              </div>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  </main>

  {#if drawerOpen}
    <div
      class="drawer-backdrop"
      class:closing={drawerClosing}
      role="button"
      tabindex="-1"
      aria-label="Close drawer"
      onclick={closeDrawer}
      onkeydown={(event) => {
        if (event.key === "Escape") closeDrawer();
      }}
    ></div>

    <div class="drawer-shell" class:closing={drawerClosing}>
      <div
        class="drawer"
        class:closing={drawerClosing}
        role="dialog"
        aria-modal="true"
      >
        <div class="drawer-handle"><div class="drawer-handle-bar"></div></div>
        <div class="drawer-header">
          {#if drawerBook}
            <div class="drawer-title-block">
              <div class="drawer-title">{drawerBook.title}</div>
              <div class="drawer-subtitle">
                {drawerBook.author ?? "unknown creator"}
              </div>
            </div>
          {:else if drawerKOReaderDocument}
            <div class="drawer-title-block">
              <div class="drawer-title">
                {drawerKOReaderDocument.title ??
                  `document ${drawerKOReaderDocument.document_hash.slice(0, 8)}`}
              </div>
              <div class="drawer-subtitle">
                {drawerKOReaderDocument.author ?? "manual device title"}
              </div>
            </div>
          {:else}
            <span class="drawer-title">
              {#if drawerTab === "track"}add title
              {:else if drawerTab === "auth"}ranobelib auth
              {:else if drawerTab === "jobs"}recent jobs
              {:else if drawerTab === "library"}collections
              {:else if drawerTab === "metadata"}opds metadata
              {:else if drawerTab === "device"}koreader sync
              {:else}title controls{/if}
            </span>
          {/if}
          <button type="button" class="drawer-close" onclick={closeDrawer}
            >✕</button
          >
        </div>

        <div class="drawer-panel">
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
                class="btn btn-outline full-width-btn"
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
                    <div class="preview-author">
                      {preview.author ?? "unknown creator"}
                    </div>
                    <div class="preview-meta">
                      {preview.available_chapters} chapters ready
                    </div>
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
                class="btn btn-solid full-width-btn"
                disabled={submitting || !bookUrl.trim() || !preview}
                onclick={() => void submitBook()}
              >
                {submitting ? "queueing..." : "track and build"}
              </button>
            </div>
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
                    {validation?.valid
                      ? "valid"
                      : validation
                        ? "failed"
                        : "idle"}
                  </div>
                </div>
              </div>

              {#if validation?.username || validation?.email}
                <div class="auth-user-copy">
                  logged in as {validation.username ?? validation.email}
                </div>
              {/if}

              {#if authSession?.authenticated}
                <div class="auth-user-copy">
                  browser session: {authSession.username}
                </div>
              {/if}

              <div class="form-field">
                <label for="access-token" class="form-label">access token</label
                >
                <textarea
                  id="access-token"
                  class="form-textarea"
                  placeholder="paste bearer token"
                  bind:value={accessToken}
                ></textarea>
              </div>
              <div class="form-field">
                <label for="refresh-token" class="form-label"
                  >refresh token</label
                >
                <textarea
                  id="refresh-token"
                  class="form-textarea"
                  placeholder="paste refresh token"
                  bind:value={refreshToken}
                ></textarea>
              </div>
              <div class="drawer-inline-actions">
                <button
                  type="button"
                  class="btn btn-outline"
                  disabled={validating}
                  onclick={() => void runValidation()}
                >
                  {validating ? "checking..." : "validate"}
                </button>
                <button
                  type="button"
                  class="btn btn-solid"
                  disabled={submitting}
                  onclick={() => void saveCredential()}
                >
                  {submitting ? "saving..." : "save tokens"}
                </button>
              </div>

              {#if authSession?.authenticated}
                <button
                  type="button"
                  class="btn btn-ghost full-width-btn"
                  onclick={() => void signOutBrowserSession()}
                >
                  sign out browser session
                </button>
              {/if}
            </div>
          {:else if drawerTab === "jobs"}
            <div class="drawer-body">
              {#if jobs.length === 0}
                <div class="drawer-empty-copy">no jobs yet</div>
              {:else}
                {#each jobs as job}
                  <div class="job-row">
                    <div>
                      <div class="job-type">
                        {jobTypeLabel(job.type)} · {jobTriggerLabel(
                          job.trigger,
                        )}
                      </div>
                      <div class="job-book-title">
                        {job.book_title ?? "library task"}
                      </div>
                      <div class="job-status {job.status}">{job.status}</div>
                    </div>
                    <div class="job-time">{formatDate(job.created_at)}</div>
                  </div>
                {/each}
              {/if}
            </div>
          {:else if drawerTab === "library"}
            <div class="drawer-body">
              <div class="form-field">
                <label for="collection-name" class="form-label"
                  >new collection</label
                >
                <input
                  id="collection-name"
                  class="form-input"
                  type="text"
                  placeholder="favorites, backlog, weekend..."
                  bind:value={collectionName}
                />
              </div>

              <button
                type="button"
                class="btn btn-solid full-width-btn"
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
                          <div class="collection-meta">
                            {collection.book_count} title{collection.book_count !==
                            1
                              ? "s"
                              : ""}
                          </div>
                        </div>
                        <button
                          type="button"
                          class="btn btn-danger btn-compact collection-delete-btn"
                          onclick={() => {
                            collectionDeleteCandidate = collection;
                          }}
                        >
                          delete
                        </button>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            </div>
          {:else if drawerTab === "metadata"}
            <div class="drawer-body">
              <div class="drawer-section">
                <div class="drawer-section-label">visible genres in opds</div>
                <div class="chip-grid">
                  {#if opdsVisibility?.genres.length}
                    {#each opdsVisibility.genres as genre}
                      <button
                        type="button"
                        class="filter-chip"
                        class:selected={pendingVisibleGenreSlugs.includes(
                          genre.slug,
                        )}
                        onclick={() => toggleNamedValue("genre", genre)}
                      >
                        {genre.name}
                      </button>
                    {/each}
                  {:else}
                    <div class="drawer-empty-copy">
                      no genres discovered yet
                    </div>
                  {/if}
                </div>
              </div>

              <div class="drawer-section">
                <div class="drawer-section-label">visible tags in opds</div>
                <div class="chip-grid">
                  {#if opdsVisibility?.tags.length}
                    {#each opdsVisibility.tags as tag}
                      <button
                        type="button"
                        class="filter-chip"
                        class:selected={pendingVisibleTagSlugs.includes(
                          tag.slug,
                        )}
                        onclick={() => toggleNamedValue("tag", tag)}
                      >
                        {tag.name}
                      </button>
                    {/each}
                  {:else}
                    <div class="drawer-empty-copy">no tags discovered yet</div>
                  {/if}
                </div>
              </div>

              <button
                type="button"
                class="btn btn-solid full-width-btn"
                disabled={savingOpdsVisibility}
                onclick={() => void saveOpdsVisibility()}
              >
                {savingOpdsVisibility ? "saving..." : "save visibility"}
              </button>
            </div>
          {:else if drawerTab === "device"}
            <div class="drawer-body">
              <div class="drawer-section">
                {#if (koreaderState?.documents.length ?? 0) === 0}
                  <div class="drawer-empty-copy">
                    no KOReader progress synced yet
                  </div>
                {:else}
                  <div class="device-list">
                    {#each koreaderState?.documents ?? [] as item}
                      <button
                        type="button"
                        class="device-row device-row-button"
                        onclick={() => {
                          selectedKOReaderDocumentId = item.id;
                        }}
                      >
                        <div>
                          <div class="collection-name">
                            {item.title ??
                              item.linked_book_title ??
                              `document ${item.document_hash.slice(0, 8)}`}
                          </div>
                          <div class="collection-meta">
                            {#if item.linked_book_title}
                              linked to {item.linked_book_title}
                            {:else}
                              {item.username} · {item.document_hash.slice(
                                0,
                                12,
                              )}
                            {/if}
                          </div>
                        </div>
                        <div class="device-side">
                          <div class="device-progress">
                            {formatPercent(item.progress_percent)}
                          </div>
                          <div class="collection-meta">
                            {formatTimestamp(item.progress_timestamp)}
                          </div>
                        </div>
                      </button>
                    {/each}
                  </div>
                {/if}
              </div>

              {#if selectedKOReaderDocument}
                <div class="drawer-section">
                  <div class="drawer-section-label">edit synced title</div>
                  <div class="form-field">
                    <label for="koreader-document-title" class="form-label"
                      >title</label
                    >
                    <input
                      id="koreader-document-title"
                      class="form-input"
                      type="text"
                      bind:value={koreaderDocumentTitle}
                    />
                  </div>
                  <div class="form-field">
                    <label for="koreader-document-author" class="form-label"
                      >author</label
                    >
                    <input
                      id="koreader-document-author"
                      class="form-input"
                      type="text"
                      bind:value={koreaderDocumentAuthor}
                    />
                  </div>
                  <div class="form-field">
                    <label for="koreader-link-book" class="form-label"
                      >link to tracked title</label
                    >
                    <Select
                      id="koreader-link-book"
                      class="form-select"
                      bind:value={koreaderLinkedBookId}
                      options={koreaderLinkOptions(books)}
                      placeholder="unlinked"
                    />
                  </div>
                  <div class="auth-user-copy">
                    {selectedKOReaderDocument.username} · {selectedKOReaderDocument.document_hash}
                  </div>
                  <button
                    type="button"
                    class="btn btn-solid full-width-btn"
                    disabled={savingKoreaderDocument}
                    onclick={() => void saveKOReaderDocument()}
                  >
                    {savingKoreaderDocument ? "saving..." : "save synced title"}
                  </button>
                </div>
              {/if}
            </div>
          {:else if drawerTab === "koreader-document" && drawerKOReaderDocument}
            <div class="drawer-body">
              <div class="status-row">
                <div class="status-cell">
                  <div class="status-cell-label">progress</div>
                  <div class="status-cell-value active">
                    {formatPercent(drawerKOReaderDocument.progress_percent)}
                  </div>
                </div>
                <div class="status-cell">
                  <div class="status-cell-label">device</div>
                  <div class="status-cell-value">
                    {drawerKOReaderDocument.device ?? "unknown"}
                  </div>
                </div>
                <div class="status-cell">
                  <div class="status-cell-label">user</div>
                  <div class="status-cell-value active">
                    {drawerKOReaderDocument.username}
                  </div>
                </div>
              </div>

              <div class="form-field">
                <label for="drawer-koreader-document-title" class="form-label"
                  >title</label
                >
                <input
                  id="drawer-koreader-document-title"
                  class="form-input"
                  type="text"
                  bind:value={koreaderDocumentTitle}
                />
              </div>
              <div class="form-field">
                <label for="drawer-koreader-document-author" class="form-label"
                  >author</label
                >
                <input
                  id="drawer-koreader-document-author"
                  class="form-input"
                  type="text"
                  bind:value={koreaderDocumentAuthor}
                />
              </div>
              <div class="form-field">
                <label for="drawer-koreader-link-book" class="form-label"
                  >link to tracked title</label
                >
                <Select
                  id="drawer-koreader-link-book"
                  class="form-select"
                  bind:value={koreaderLinkedBookId}
                  options={koreaderLinkOptions(books)}
                  placeholder="unlinked"
                />
              </div>
              <div class="auth-user-copy">
                {drawerKOReaderDocument.username} · {drawerKOReaderDocument.document_hash}
              </div>
              <button
                type="button"
                class="btn btn-solid full-width-btn"
                disabled={savingKoreaderDocument}
                onclick={() => void saveKOReaderDocument()}
              >
                {savingKoreaderDocument ? "saving..." : "save synced title"}
              </button>
            </div>
          {:else if drawerBook}
            <div class="drawer-body">
              <div class="form-field">
                <label for="book-title" class="form-label">title</label>
                <input
                  id="book-title"
                  class="form-input"
                  type="text"
                  bind:value={preferenceTitle}
                />
              </div>

              <div class="form-field">
                <label for="book-author" class="form-label">author</label>
                <input
                  id="book-author"
                  class="form-input"
                  type="text"
                  bind:value={preferenceAuthor}
                />
              </div>

              <div class="form-field">
                <div class="rating-row">
                  <button
                    type="button"
                    class="favorite-toggle"
                    class:active={preferenceIsFavorite}
                    aria-pressed={preferenceIsFavorite}
                    aria-label={preferenceIsFavorite
                      ? "Remove favorite"
                      : "Mark favorite"}
                    onclick={() => {
                      preferenceIsFavorite = !preferenceIsFavorite;
                    }}
                  >
                    <HeartStraightIcon
                      size={16}
                      weight={preferenceIsFavorite ? "fill" : "regular"}
                    />
                  </button>
                  <StarPicker
                    value={preferenceRating ? Number(preferenceRating) : 0}
                    size={18}
                    onChange={(value) => {
                      preferenceRating = value > 0 ? String(value) : "";
                    }}
                  />
                </div>
              </div>

              {#if collections.length > 0}
                <div class="drawer-section">
                  <div class="drawer-section-label">collections</div>
                  <div class="chip-grid">
                    {#each collections as collection}
                      <button
                        type="button"
                        class="filter-chip"
                        class:selected={preferenceCollectionIds.includes(
                          collection.id,
                        )}
                        onclick={() => toggleCollectionValue(collection.id)}
                      >
                        {collection.name}
                      </button>
                    {/each}
                  </div>
                </div>
              {/if}

              <div class="form-field">
                <label for="book-comment" class="form-label">comment</label>
                <textarea
                  id="book-comment"
                  class="form-textarea"
                  placeholder="private note"
                  bind:value={preferenceComment}
                ></textarea>
              </div>

              <div class="form-field">
                <label for="book-branch-select" class="form-label">branch</label
                >
                <Select
                  id="book-branch-select"
                  class="form-select"
                  value={branchSelectValue(drawerBook)}
                  options={branchOptions(drawerBook.branches)}
                  placeholder="default branch"
                  disabled={actionBookId === drawerBook.book_id ||
                    drawerBook.branches.length === 0}
                  onValueChange={(value) =>
                    void changeBookBranch(drawerBook.book_id, value || null)}
                />
              </div>

              <div class="book-drawer-actions">
                <button
                  type="button"
                  class="btn btn-solid"
                  disabled={savingPreferences}
                  onclick={() => void saveBookPreferences()}
                >
                  save
                </button>
                <button
                  type="button"
                  class="btn btn-outline"
                  disabled={actionBookId === drawerBook.book_id}
                  onclick={() => void runBookAction(drawerBook.book_id)}
                >
                  check now
                </button>
                {#if artifactUrl(drawerBook)}
                  <a href={artifactUrl(drawerBook)} class="btn btn-ghost"
                    >download epub</a
                  >
                {/if}
                <button
                  type="button"
                  class="btn btn-danger"
                  disabled={actionBookId === drawerBook.book_id}
                  onclick={() => void removeBook(drawerBook)}
                >
                  delete
                </button>
              </div>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <div class="fab-group">
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("jobs")}
      title="Recent jobs"
      aria-label="Recent jobs"
    >
      <ClockCounterClockwiseIcon size={20} weight="bold" />
    </button>
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("library")}
      title="Collections"
      aria-label="Collections"
    >
      <BooksIcon size={20} weight="bold" />
    </button>
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("metadata")}
      title="OPDS metadata"
      aria-label="OPDS metadata"
    >
      <EyeIcon size={20} weight="bold" />
    </button>
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("device")}
      title="KOReader sync"
      aria-label="KOReader sync"
    >
      <ArrowsClockwiseIcon size={20} weight="bold" />
    </button>
    <button
      type="button"
      class="fab fab-secondary"
      onclick={() => openDrawer("auth")}
      title="Auth settings"
      aria-label="Auth settings"
    >
      <ShieldCheckIcon size={18} weight="bold" />
    </button>
    <button
      type="button"
      class="fab fab-primary"
      onclick={() => openDrawer("track")}
      title="Add title"
      aria-label="Add a title"
    >
      <PlusIcon size={22} weight="bold" />
    </button>
  </div>

  <ToastContainer />
  <ConfirmDialog
    open={collectionDeleteCandidate !== null}
    title="delete collection"
    description={collectionDeleteCandidate
      ? `Remove "${collectionDeleteCandidate.name}" from the library?`
      : ""}
    confirmLabel="delete"
    cancelLabel="cancel"
    danger={true}
    onConfirm={() => void confirmRemoveCollection()}
    onCancel={() => {
      collectionDeleteCandidate = null;
    }}
  />
</div>
{/if}
