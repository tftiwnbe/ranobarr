<script lang="ts">
  import { onMount } from "svelte";
  import Alert from "./lib/components/Alert.svelte";
  import Button from "./lib/components/Button.svelte";
  import InputField from "./lib/components/InputField.svelte";
  import Panel from "./lib/components/Panel.svelte";
  import StarField from "./lib/components/StarField.svelte";
  import ToastContainer from "./lib/components/ToastContainer.svelte";
  import { toast } from "./lib/components/toast-store.svelte";
  import Tabs, { type TabItem } from "./lib/components/Tabs.svelte";
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
    type TrackedBook
  } from "./lib/api";

  type BookCard = TrackedBook & {
    latestArtifact: ArtifactSummary | null;
  };

  let books = $state<BookCard[]>([]);
  let jobs = $state<JobSummary[]>([]);
  let credential = $state<CredentialView | null>(null);
  let validation = $state<CredentialValidation | null>(null);

  let loading = $state(true);
  let submitting = $state(false);
  let validating = $state(false);
  let actionBookId = $state<string | null>(null);

  let accessToken = $state("");
  let refreshToken = $state("");
  let bookUrl = $state("");
  let branchMode = $state("default");
  let sideTab = $state("track");

  async function loadDashboard() {
    loading = true;
    try {
      credential = await getCredential();
      const [trackedBooks, recentJobs] = await Promise.all([listTrackedBooks(), listJobs()]);
      const artifactPairs = await Promise.all(
        trackedBooks.map(async (book) => ({
          bookId: book.book_id,
          artifact: await latestArtifact(book.book_id)
        }))
      );
      const artifactMap = new Map(artifactPairs.map((entry) => [entry.bookId, entry.artifact]));
      books = trackedBooks.map((book) => ({
        ...book,
        latestArtifact: artifactMap.get(book.book_id) ?? null
      }));
      jobs = recentJobs.slice(0, 8);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "failed to load dashboard");
    } finally {
      loading = false;
    }
  }

  async function saveCredential() {
    submitting = true;
    try {
      credential = await putCredential({
        access_token: accessToken.trim() || null,
        refresh_token: refreshToken.trim() || null
      });
      toast.success("stored ranobelib credentials");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "failed to store credentials");
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
      toast.error(error instanceof Error ? error.message : "failed to validate credentials");
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
        selected_branch_id: null
      });
      bookUrl = "";
      toast.success("tracked title added");
      await loadDashboard();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "failed to track title");
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
        toast.success("queued rebuild");
      }
      await loadDashboard();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `failed to ${action} title`);
    } finally {
      actionBookId = null;
    }
  }

  function artifactUrl(book: BookCard): string | null {
    return book.latestArtifact ? `/api/v1/artifacts/${book.latestArtifact.id}/download` : null;
  }

  function formatDate(value: string | null): string {
    if (!value) return "not yet";
    return new Date(value).toLocaleString();
  }

  function formatBytes(value: number): string {
    if (value < 1024) return `${value} b`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} kb`;
    return `${(value / (1024 * 1024)).toFixed(1)} mb`;
  }

  const sideTabs = $derived<TabItem[]>([
    { value: "track", label: "track" },
    { value: "auth", label: "auth" },
    { value: "jobs", label: "jobs", count: jobs.length }
  ]);

  onMount(loadDashboard);
</script>

<svelte:head>
  <title>Ranobarr</title>
  <meta
    name="description"
    content="Track RanobeLib titles, validate credentials, and build EPUB artifacts from one dashboard."
  />
</svelte:head>

<div class="page-shell">
  <div class="grid-overlay"></div>
  <StarField count={44} />
  <div class="orbital-ring" aria-hidden="true">
    <svg viewBox="0 0 200 200">
      <ellipse cx="100" cy="100" rx="95" ry="28" fill="none" stroke="rgba(140,140,160,0.24)" stroke-width="0.45"></ellipse>
      <ellipse cx="100" cy="100" rx="74" ry="22" fill="none" stroke="rgba(140,140,160,0.16)" stroke-width="0.35" transform="rotate(60 100 100)"></ellipse>
    </svg>
  </div>

  <main class="page-wrap">
    <section class="metrics-grid" style="margin-bottom:1rem;">
      <article class="metric-card">
        <span class="metric-value">{books.length}</span>
        <div class="metric-label">tracked titles</div>
      </article>
      <article class="metric-card">
        <span class="metric-value">{jobs.filter((job) => job.status === "running").length}</span>
        <div class="metric-label">running jobs</div>
      </article>
      <article class="metric-card">
        <span class="metric-value">{jobs.filter((job) => job.status === "failed").length}</span>
        <div class="metric-label">failed jobs</div>
      </article>
    </section>

    <section class="dashboard-grid">
      <div class="main-column">
        <Panel eyebrow="library" title="tracked titles" actionLabel={loading ? "refreshing..." : "refresh"} actionDisabled={loading} onAction={loadDashboard}>
          {#if loading}
            <div class="empty-state">loading dashboard...</div>
          {:else if books.length === 0}
            <div class="empty-state">no titles tracked yet</div>
          {:else}
            <div class="book-grid">
              {#each books as book}
                <article class="book-card">
                  <div class="book-top">
                    <div>
                      <div class="eyebrow">{book.slug}</div>
                      <h3 class="book-name">{book.title}</h3>
                    </div>
                    <div class="chip">{book.branch_mode}</div>
                  </div>

                  <div class="chip-row">
                    <div class="chip">{book.known_remote_chapters} synced chapters</div>
                    <div class="chip">{book.last_remote_chapter_key ?? "no remote key"}</div>
                  </div>

                  <div class="book-meta-grid">
                    <div>
                      <div class="meta-label">last checked</div>
                      <div class="meta-value">{formatDate(book.last_checked_at)}</div>
                    </div>
                    <div>
                      <div class="meta-label">latest epub</div>
                      <div class="meta-value">
                        {#if book.latestArtifact}
                          {formatBytes(book.latestArtifact.file_size_bytes)}
                        {:else}
                          missing
                        {/if}
                      </div>
                    </div>
                  </div>

                  <div class="action-row">
                    <Button variant="outline" disabled={actionBookId === book.book_id} onclick={() => runBookAction(book.book_id, "check")}>
                      check updates
                    </Button>
                    <Button disabled={actionBookId === book.book_id} onclick={() => runBookAction(book.book_id, "build")}>
                      build epub
                    </Button>
                    {#if artifactUrl(book)}
                      <Button variant="ghost" href={artifactUrl(book)}>download latest</Button>
                    {/if}
                  </div>
                </article>
              {/each}
            </div>
          {/if}
        </Panel>
      </div>

      <div class="side-column">
        <Panel
          eyebrow="controls"
          title={sideTab === "track" ? "add a title" : sideTab === "auth" ? "ranobelib session" : "recent activity"}
          actionLabel={sideTab === "auth" ? (validating ? "checking..." : "validate") : undefined}
          actionDisabled={sideTab === "auth" ? validating : false}
          onAction={sideTab === "auth" ? runValidation : undefined}
        >
          <div class="stack">
            <Tabs tabs={sideTabs} value={sideTab} onValueChange={(value) => (sideTab = value)} />

            {#if sideTab === "track"}
              <form class="split-form" onsubmit={(event) => {
                event.preventDefault();
                void submitBook();
              }}>
                <InputField label="ranobelib url" bind:value={bookUrl} placeholder="https://ranobelib.me/ru/book/..." />
                <label class="stack" style="gap:0.35rem;">
                  <span class="eyebrow">branch strategy</span>
                  <select bind:value={branchMode} style="width:100%;height:48px;padding:0 1rem;border:1px solid var(--line);background:var(--void-2);color:var(--text);">
                    <option value="default">default branch</option>
                    <option value="selected">selected branch later</option>
                  </select>
                </label>
                <Button type="submit" loading={submitting}>track title</Button>
              </form>
            {:else if sideTab === "auth"}
              <div class="status-grid">
                <div class="status-card">
                  <div class="status-label">access token</div>
                  <div class:active={credential?.has_access_token} class="status-value">{credential?.has_access_token ? "stored" : "missing"}</div>
                </div>
                <div class="status-card">
                  <div class="status-label">refresh token</div>
                  <div class:active={credential?.has_refresh_token} class="status-value">{credential?.has_refresh_token ? "stored" : "missing"}</div>
                </div>
                <div class="status-card">
                  <div class="status-label">remote check</div>
                  <div class:active={validation?.valid} class="status-value">{validation?.valid ? "valid" : validation ? "failed" : "idle"}</div>
                </div>
              </div>

              {#if validation}
                <div class="status-card">
                  <div class="status-label">validation</div>
                  <div class="meta-value">{validation.username ?? validation.email ?? validation.error}</div>
                </div>
              {/if}

              <form class="split-form" onsubmit={(event) => {
                event.preventDefault();
                void saveCredential();
              }}>
                <InputField label="access token" bind:value={accessToken} multiline={true} placeholder="paste bearer token" />
                <InputField label="refresh token" bind:value={refreshToken} multiline={true} placeholder="paste refresh token" />
                <Button type="submit" loading={submitting}>save tokens</Button>
              </form>
            {:else}
              {#if jobs.length === 0}
                <div class="empty-state">no jobs recorded yet</div>
              {:else}
                <div class="job-list">
                  {#each jobs as job}
                    <article class="list-row">
                      <div>
                        <div class="eyebrow">{job.type}</div>
                        <strong>{job.status}</strong>
                      </div>
                      <div style="text-align:right;">
                        <p class="muted">{job.book_id ?? "global job"}</p>
                        <div class="dim">{formatDate(job.created_at)}</div>
                      </div>
                    </article>
                  {/each}
                </div>
              {/if}
            {/if}
          </div>
        </Panel>
      </div>
    </section>
  </main>

  <ToastContainer />
</div>
