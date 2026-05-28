<script lang="ts">
  import { onMount } from "svelte";
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

  let books: BookCard[] = [];
  let jobs: JobSummary[] = [];
  let credential: CredentialView | null = null;
  let validation: CredentialValidation | null = null;

  let loading = true;
  let submitting = false;
  let validating = false;
  let actionBookId: string | null = null;
  let errorMessage = "";
  let successMessage = "";

  let accessToken = "";
  let refreshToken = "";
  let bookUrl = "";
  let branchMode = "default";

  async function loadDashboard() {
    loading = true;
    errorMessage = "";
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
      errorMessage = error instanceof Error ? error.message : "Failed to load dashboard";
    } finally {
      loading = false;
    }
  }

  async function saveCredential() {
    submitting = true;
    errorMessage = "";
    successMessage = "";
    try {
      credential = await putCredential({
        access_token: accessToken.trim() || null,
        refresh_token: refreshToken.trim() || null
      });
      successMessage = "Stored RanobeLib credentials.";
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Failed to store credentials";
    } finally {
      submitting = false;
    }
  }

  async function runValidation() {
    validating = true;
    errorMessage = "";
    successMessage = "";
    try {
      validation = await validateCredential();
      successMessage = validation.valid ? "Credential validated against RanobeLib." : "Credential check failed.";
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Failed to validate credentials";
    } finally {
      validating = false;
    }
  }

  async function submitBook() {
    submitting = true;
    errorMessage = "";
    successMessage = "";
    try {
      await createTrackedBook({
        url: bookUrl.trim(),
        branch_mode: branchMode,
        selected_branch_id: null
      });
      bookUrl = "";
      successMessage = "Tracked title added.";
      await loadDashboard();
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Failed to track title";
    } finally {
      submitting = false;
    }
  }

  async function runBookAction(bookId: string, action: "check" | "build") {
    actionBookId = bookId;
    errorMessage = "";
    successMessage = "";
    try {
      if (action === "check") {
        await triggerCheck(bookId);
        successMessage = "Queued update check.";
      } else {
        await triggerBuild(bookId);
        successMessage = "Queued rebuild.";
      }
      await loadDashboard();
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : `Failed to ${action} title`;
    } finally {
      actionBookId = null;
    }
  }

  function artifactUrl(book: BookCard): string | null {
    if (!book.latestArtifact) {
      return null;
    }
    return `/api/v1/artifacts/${book.latestArtifact.id}/download`;
  }

  function formatDate(value: string | null): string {
    if (!value) {
      return "Not yet";
    }
    return new Date(value).toLocaleString();
  }

  function formatBytes(value: number): string {
    if (value < 1024) {
      return `${value} B`;
    }
    if (value < 1024 * 1024) {
      return `${(value / 1024).toFixed(1)} KB`;
    }
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  onMount(loadDashboard);
</script>

<svelte:head>
  <title>Ranobarr</title>
  <meta
    name="description"
    content="Track RanobeLib titles, validate credentials, and build EPUB artifacts from one dashboard."
  />
</svelte:head>

<div class="shell">
  <div class="grain"></div>

  <header class="hero">
    <div class="hero-copy">
      <p class="eyebrow">RanobeLib Tracker</p>
      <h1>One quiet control room for update checks and EPUB rebuilds.</h1>
      <p class="lede">
        Static Svelte frontend, Python backend, local storage. No extra service split.
      </p>
    </div>
    <div class="hero-metrics">
      <article>
        <span>{books.length}</span>
        <p>tracked titles</p>
      </article>
      <article>
        <span>{jobs.filter((job) => job.status === "running").length}</span>
        <p>running jobs</p>
      </article>
      <article>
        <span>{jobs.filter((job) => job.status === "failed").length}</span>
        <p>failed jobs</p>
      </article>
    </div>
  </header>

  {#if errorMessage}
    <div class="banner error">{errorMessage}</div>
  {/if}

  {#if successMessage}
    <div class="banner success">{successMessage}</div>
  {/if}

  <main class="dashboard">
    <section class="panel auth-panel">
      <div class="panel-heading">
        <div>
          <p class="panel-kicker">Source auth</p>
          <h2>RanobeLib session</h2>
        </div>
        <button class="ghost-button" on:click={runValidation} disabled={validating}>
          {validating ? "Checking..." : "Validate"}
        </button>
      </div>

      <div class="status-strip">
        <div>
          <span class:active={credential?.has_access_token}>Access token</span>
          <strong>{credential?.has_access_token ? "stored" : "missing"}</strong>
        </div>
        <div>
          <span class:active={credential?.has_refresh_token}>Refresh token</span>
          <strong>{credential?.has_refresh_token ? "stored" : "missing"}</strong>
        </div>
        <div>
          <span class:active={validation?.valid}>Remote check</span>
          <strong>{validation?.valid ? "valid" : validation ? "failed" : "not run"}</strong>
        </div>
      </div>

      {#if validation}
        <div class="validation-card">
          <p>{validation.valid ? "Authenticated user" : "Last validation result"}</p>
          <strong>{validation.username ?? validation.email ?? validation.error}</strong>
        </div>
      {/if}

      <form class="stack-form" on:submit|preventDefault={saveCredential}>
        <label>
          <span>Access token</span>
          <textarea bind:value={accessToken} rows="3" placeholder="Paste bearer token"></textarea>
        </label>
        <label>
          <span>Refresh token</span>
          <textarea bind:value={refreshToken} rows="3" placeholder="Paste refresh token"></textarea>
        </label>
        <button class="solid-button" type="submit" disabled={submitting}>Save tokens</button>
      </form>
    </section>

    <section class="panel intake-panel">
      <div class="panel-heading">
        <div>
          <p class="panel-kicker">Tracking</p>
          <h2>Add a title</h2>
        </div>
      </div>

      <form class="stack-form" on:submit|preventDefault={submitBook}>
        <label>
          <span>RanobeLib URL</span>
          <input bind:value={bookUrl} type="url" placeholder="https://ranobelib.me/ru/book/..." />
        </label>
        <label>
          <span>Branch strategy</span>
          <select bind:value={branchMode}>
            <option value="default">Default branch</option>
            <option value="selected">Selected branch later</option>
          </select>
        </label>
        <button class="solid-button" type="submit" disabled={submitting}>Track title</button>
      </form>
    </section>

    <section class="panel library-panel">
      <div class="panel-heading">
        <div>
          <p class="panel-kicker">Library</p>
          <h2>Tracked titles</h2>
        </div>
        <button class="ghost-button" on:click={loadDashboard} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {#if loading}
        <div class="empty-state">Loading dashboard...</div>
      {:else if books.length === 0}
        <div class="empty-state">No titles tracked yet.</div>
      {:else}
        <div class="book-grid">
          {#each books as book}
            <article class="book-card">
              <div class="book-meta">
                <p class="book-slug">{book.slug}</p>
                <h3>{book.title}</h3>
                <div class="book-chips">
                  <span>{book.known_remote_chapters} synced chapters</span>
                  <span>{book.last_remote_chapter_key ?? "no remote key yet"}</span>
                </div>
              </div>

              <dl class="book-stats">
                <div>
                  <dt>Last checked</dt>
                  <dd>{formatDate(book.last_checked_at)}</dd>
                </div>
                <div>
                  <dt>Build artifact</dt>
                  <dd>
                    {#if book.latestArtifact}
                      {formatBytes(book.latestArtifact.file_size_bytes)}
                    {:else}
                      Missing
                    {/if}
                  </dd>
                </div>
              </dl>

              <div class="book-actions">
                <button
                  class="ghost-button"
                  on:click={() => runBookAction(book.book_id, "check")}
                  disabled={actionBookId === book.book_id}
                >
                  Check updates
                </button>
                <button
                  class="solid-button"
                  on:click={() => runBookAction(book.book_id, "build")}
                  disabled={actionBookId === book.book_id}
                >
                  Build EPUB
                </button>
                {#if artifactUrl(book)}
                  <a class="download-link" href={artifactUrl(book)} target="_blank">Download latest</a>
                {/if}
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </section>

    <section class="panel jobs-panel">
      <div class="panel-heading">
        <div>
          <p class="panel-kicker">Jobs</p>
          <h2>Recent activity</h2>
        </div>
      </div>

      {#if jobs.length === 0}
        <div class="empty-state">No jobs recorded yet.</div>
      {:else}
        <div class="job-list">
          {#each jobs as job}
            <article class="job-row">
              <div>
                <p class="job-type">{job.type}</p>
                <strong>{job.status}</strong>
              </div>
              <div>
                <p>{job.book_id ?? "global job"}</p>
                <span>{formatDate(job.created_at)}</span>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </section>
  </main>
</div>
