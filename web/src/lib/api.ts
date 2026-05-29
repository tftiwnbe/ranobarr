export type NamedTagSummary = {
  name: string;
  slug: string;
};

export type BranchSummary = {
  id: string;
  name: string;
  chapter_count: number;
  team_names: string[];
  display: string;
};

export type CollectionSummary = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  sort_order: number;
  book_count: number;
};

export type CredentialView = {
  provider: string;
  has_access_token: boolean;
  has_refresh_token: boolean;
  expires_at: string | null;
  updated_at: string;
};

export type CredentialValidation = {
  provider: string;
  valid: boolean;
  authenticated: boolean;
  user_id: string | null;
  username: string | null;
  email: string | null;
  error: string | null;
};

export type TrackedBook = {
  book_id: string;
  slug: string;
  title: string;
  author: string | null;
  cover_url: string | null;
  available_chapters: number;
  known_remote_chapters: number;
  genres: NamedTagSummary[];
  tags: NamedTagSummary[];
  opds_visible_genres: NamedTagSummary[];
  opds_visible_tags: NamedTagSummary[];
  branch_mode: string;
  selected_branch_id: string | null;
  selected_branch_label: string | null;
  branches: BranchSummary[];
  enabled: boolean;
  is_favorite: boolean;
  is_current: boolean;
  rating: number | null;
  comment: string | null;
  collections: CollectionSummary[];
  created_at: string;
  updated_at: string;
  last_checked_at: string | null;
  last_remote_chapter_key: string | null;
};

export type PreviewBook = {
  slug: string;
  title: string;
  author: string | null;
  summary: string | null;
  cover_url: string | null;
  available_chapters: number;
  branches: BranchSummary[];
  genres: NamedTagSummary[];
  tags: NamedTagSummary[];
};

export type JobSummary = {
  id: string;
  type: string;
  status: string;
  book_id: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ArtifactSummary = {
  id: string;
  book_id: string;
  format: string;
  relative_path: string;
  chapter_count: number;
  file_size_bytes: number;
  created_at: string;
};

export type TrackBookPayload = {
  url: string;
  branch_mode: string;
  selected_branch_id: string | null;
};

export type BookPreferencesPayload = {
  opds_visible_genre_slugs?: string[] | null;
  opds_visible_tag_slugs?: string[] | null;
  is_favorite?: boolean | null;
  is_current?: boolean | null;
  rating?: number | null;
  comment?: string | null;
  collection_ids?: string[] | null;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail ?? `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function getCredential(): Promise<CredentialView | null> {
  return apiFetch<CredentialView | null>("/api/v1/source-auth/ranobelib");
}

export async function putCredential(payload: {
  access_token: string | null;
  refresh_token: string | null;
}): Promise<CredentialView> {
  return apiFetch<CredentialView>("/api/v1/source-auth/ranobelib", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function validateCredential(): Promise<CredentialValidation> {
  return apiFetch<CredentialValidation>("/api/v1/source-auth/ranobelib/validate", {
    method: "POST"
  });
}

export async function listTrackedBooks(sort: "added" | "updated" | "title" = "updated"): Promise<TrackedBook[]> {
  return apiFetch<TrackedBook[]>(`/api/v1/tracking/books?sort=${sort}`);
}

export async function previewTrackedBook(url: string): Promise<PreviewBook> {
  return apiFetch<PreviewBook>("/api/v1/tracking/preview", {
    method: "POST",
    body: JSON.stringify({ url })
  });
}

export async function createTrackedBook(payload: TrackBookPayload): Promise<void> {
  await apiFetch("/api/v1/tracking/books", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateTrackedBookBranch(bookId: string, selectedBranchId: string | null): Promise<void> {
  await apiFetch(`/api/v1/tracking/books/${bookId}/branch`, {
    method: "PATCH",
    body: JSON.stringify({ selected_branch_id: selectedBranchId })
  });
}

export async function deleteTrackedBook(bookId: string): Promise<void> {
  await apiFetch(`/api/v1/tracking/books/${bookId}`, {
    method: "DELETE"
  });
}

export async function updateBookPreferences(bookId: string, payload: BookPreferencesPayload): Promise<TrackedBook> {
  return apiFetch<TrackedBook>(`/api/v1/tracking/books/${bookId}/preferences`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function triggerCheck(bookId: string): Promise<void> {
  await apiFetch(`/api/v1/tracking/books/${bookId}/check`, {
    method: "POST"
  });
}

export async function latestArtifact(bookId: string): Promise<ArtifactSummary | null> {
  return apiFetch<ArtifactSummary | null>(`/api/v1/artifacts/books/${bookId}/latest?format=epub`);
}

export async function listJobs(): Promise<JobSummary[]> {
  return apiFetch<JobSummary[]>("/api/v1/jobs");
}

export async function listCollections(): Promise<CollectionSummary[]> {
  return apiFetch<CollectionSummary[]>("/api/v1/library/collections");
}

export async function createCollection(payload: {
  name: string;
  description?: string | null;
  sort_order?: number;
}): Promise<CollectionSummary> {
  return apiFetch<CollectionSummary>("/api/v1/library/collections", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function deleteCollection(collectionId: string): Promise<void> {
  await apiFetch(`/api/v1/library/collections/${collectionId}`, {
    method: "DELETE"
  });
}
