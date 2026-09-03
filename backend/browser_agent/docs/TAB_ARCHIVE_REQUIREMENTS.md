# Browser Agent Tab Archive — Requirements Specification

## 1. Document Purpose

This document defines the requirements for extending Browser Agent Tabs into a persistent tab archive and retrieval system. The feature is intended for users who keep many browser tabs open, want to reduce memory and battery usage, and still need to find and reopen useful pages after days, months, or years.

This document is the implementation baseline for the feature. It records the agreed behavior before code changes begin.

## 2. Problem Statement

Keeping a large number of browser tabs open has several disadvantages:

- Open tabs consume memory and may increase CPU and battery usage.
- Useful tabs become difficult to find among many low-value tabs.
- Standard browser bookmarks become ineffective when the collection grows without strong retrieval and ranking capabilities.
- A page that is not useful today may become valuable again much later.
- Users need a reliable end-of-day workflow that stores useful tabs and closes them without losing information.

Browser Agent already supports listing and closing live browser tabs. The new feature will add persistent archival, retrieval, metadata, semantic search, and safe batch restoration.

## 3. Goals

The feature shall:

1. Separate currently open browser tabs from persistently archived tabs.
2. Allow selected live tabs to be archived and closed safely.
3. Provide a safe end-of-day action for archiving eligible open tabs in bulk.
4. Allow archived tabs to be selected across multiple searches and reopened in one operation.
5. Support keyword, structured, and semantic retrieval.
6. Track usage history so frequently reused tabs rank higher.
7. Allow permanent protection of timeless resources through an Eternal flag.
8. Allow user comments and labels to improve future retrieval.
9. Detect potentially unavailable links without deleting data automatically.
10. Continue to provide basic archive and keyword search behavior when semantic indexing is unavailable.

## 4. Non-Goals

The first implementation does not need to:

- Replace the native browser bookmark system.
- Synchronize data across multiple computers.
- Reconstruct the original browser window layout during restore.
- Build a Knowledge Vault node-and-edge knowledge graph.
- Use an AI model to answer questions about archived tabs.
- Automatically delete old or low-heat records.
- Store browser cookies, page bodies, or authenticated page content.
- Guarantee that an authenticated page is usable based only on an HTTP health check.

## 5. Terminology

### 5.1 Live Tab

A browser tab that currently exists in a real browser window and is reported by the Browser Agent extension.

### 5.2 Archived Tab

A persistent database record representing a useful page. An archived record is shown in the Archive area when its normalized URL is not currently open in the browser.

### 5.3 Archive Operation

An operation that persists or updates selected tab records and then closes the corresponding live browser tabs after persistence succeeds.

### 5.4 Restore Operation

An operation that opens selected archived URLs in the browser and updates usage metadata only for URLs that were opened successfully.

### 5.5 Dynamic Heat

A computed ranking signal derived from usage frequency and recency. It is not directly edited by the user.

### 5.6 Eternal

A user-controlled Boolean flag for resources that should remain protected regardless of age or low usage. Eternal is independent from Dynamic Heat.

### 5.7 Age

A derived duration based primarily on the most recent successful restore time. If the tab has never been restored, the most recent archive time is used. Age is used for ranking and maintenance but is not displayed directly in the main list.

## 6. Confirmed Product Decisions

The following decisions are fixed for the initial implementation:

- Dynamic Heat is automatic; users do not manually assign high, medium, or low heat.
- Eternal is a separate manual switch.
- Each archived record supports a user-editable comment.
- The comment participates in keyword and semantic search.
- Labels participate in keyword, structured, and semantic search.
- The default restore destination is one new browser window.
- Users may choose to restore into the current browser window.
- Records with the same normalized URL are merged rather than duplicated.
- The end-of-day archive action supports safe bulk archival and excludes unsafe or protected tabs by default.

## 7. User Experience Requirements

## 7.1 Main Tabs Page

The existing Browser Agent Tabs page shall be extended with two primary areas:

- Live
- Archive

The page shall show a persistent selection summary so selections survive search and filter changes.

### 7.1.1 Main List Fields

The compact list shall prioritize:

- Selection checkbox
- Favicon
- Title
- Dynamic Heat indicator
- Eternal indicator
- Link health indicator
- Labels when space permits

The compact list shall not directly display:

- Full URL
- Browser window ID
- Raw age duration

The URL and detailed metadata shall remain available through a tooltip, details panel, or drawer so users can verify a target before opening it.

## 7.2 Live Area

The Live area shall represent the current state returned by the browser extension.

It shall support:

- Refreshing the live browser state.
- Searching and filtering live tabs.
- Selecting individual tabs.
- Selecting all currently visible eligible tabs.
- Archiving selected tabs.
- Running a safe end-of-day archive operation.
- Retaining existing close, merge-window, and group-by-domain capabilities where appropriate.

A Live record that already exists in the archive database shall display its stored comment, labels, heat, Eternal state, and usage counters.

## 7.3 Archive Area

The Archive area shall support:

- Keyword search.
- Semantic search when available.
- Filtering by label, domain, Eternal state, Dynamic Heat level, and health status.
- Sorting by relevance, heat, most recently opened, most recently archived, open count, and title.
- Selecting results across multiple searches.
- Editing title, comment, labels, and Eternal state.
- Restoring selected records.
- Removing records only through an explicit user action.

## 7.4 Selection Basket

Selections shall be independent from the current search result set.

The Selection Basket shall:

- Retain selected archived records when the search query changes.
- Retain selections when filters change.
- Show the total selected count.
- Allow users to inspect selected records.
- Allow individual records to be removed from the basket.
- Provide a clear-all action.
- Be cleared only after a fully successful restore or an explicit user action.
- Retain failed items after a partially successful restore.

## 7.5 Archive Workflow

### 7.5.1 Archive Selected

When the user archives selected live tabs, the system shall:

1. Validate that each selected tab is eligible.
2. Persist or update all eligible records before closing browser tabs.
3. Close only tabs whose records were persisted successfully.
4. Record the actual extension result.
5. Increase `archive_count` only for successfully persisted and closed tabs.
6. Refresh the Live and Archive areas after completion.
7. Report partial failures without losing successful work.

A database failure shall never cause the corresponding browser tab to close.

### 7.5.2 End-of-Day Archive

The page shall provide a safe bulk archive action.

By default, it shall exclude:

- Pinned tabs.
- Browser Agent pages.
- Browser internal URLs such as browser settings and extension pages.
- Unsupported URL schemes.
- Tabs matching user-configured exclusion rules.

Before execution, the UI shall show a preview containing:

- Number of tabs to archive.
- Number of tabs to exclude.
- Exclusion reasons.
- A list or expandable summary of affected tabs.

The user shall confirm the operation before any browser tab is closed.

## 7.6 Restore Workflow

The restore dialog shall offer:

- Open in one new window, selected by default.
- Open in the current browser window.

The system shall:

1. Check whether each normalized URL is already live.
2. Focus an existing tab by default instead of opening a duplicate.
3. Allow future support for an explicit duplicate-open option.
4. Ask the extension to open all remaining selected URLs.
5. Receive per-record success or failure results.
6. Increase `open_count` only after successful open or focus.
7. Update `last_opened_at` only after successful open or focus.
8. Move successfully restored records into the Live area after synchronization.
9. Keep failed records in the Archive area and Selection Basket.

## 8. Data Requirements

The existing `browser_tab` table is a download queue and shall not be reused for archived tab records.

## 8.1 Archived Tab Record

Each archived tab record shall contain at least:

- `id`
- `normalized_url`
- `url`
- `title`
- `domain`
- `favicon_url`
- `comment`
- `eternal`
- `created_at`
- `first_archived_at`
- `last_archived_at`
- `last_opened_at`
- `last_seen_at`
- `open_count`
- `archive_count`
- `health_status`
- `last_checked_at`
- `last_http_status`
- `final_url`

`normalized_url` shall be unique.

## 8.2 Label Record

Each label shall contain at least:

- `id`
- `name`
- `created_at`

Label names shall be unique after normalization.

Archived tabs and labels shall have a many-to-many relationship.

## 8.3 Vector Record

Each semantic index record shall contain at least:

- `tab_id`
- `embedding`
- `content_hash`
- `model_name`
- `updated_at`

The content hash shall determine whether the vector must be regenerated.

## 8.4 Archive Batch Record

Each bulk archive operation should record:

- Batch identifier
- Creation time
- Requested tab count
- Persisted tab count
- Closed tab count
- Failed tab count
- Optional source window grouping metadata

The initial restore workflow does not need to reconstruct original windows, but preserving batch metadata enables future support.

## 9. URL Normalization and Deduplication

The system shall merge records with the same normalized URL.

URL normalization shall:

- Lowercase the host.
- Remove the fragment.
- Normalize default ports.
- Normalize insignificant trailing slash differences.
- Remove known tracking parameters such as `utm_*`.
- Preserve query parameters that may change page identity.
- Preserve the original URL separately.

The implementation shall not remove all query parameters indiscriminately.

When the same normalized URL is archived again, the system shall:

- Update the title and favicon from the live tab when non-empty.
- Preserve the existing comment, labels, and Eternal flag.
- Update `last_archived_at`.
- Increase `archive_count` after successful closure.
- Avoid creating a duplicate record.

## 10. Time and Usage Semantics

- `created_at` records the first database insertion and never resets.
- `first_archived_at` records the first successful archive and never resets.
- `last_archived_at` records the latest successful archive.
- `last_opened_at` records the latest successful restore or focus through this tool.
- `last_seen_at` records the latest time the URL was observed as a live browser tab.
- `open_count` counts successful restores or focuses initiated through this tool.
- `archive_count` counts successful archive-and-close cycles.

Age shall be derived rather than persisted:

- Use `last_opened_at` when available.
- Otherwise use `last_archived_at`.
- Otherwise use `created_at`.

Archiving a previously restored tab naturally resets its effective age through the new `last_archived_at` value; historical timestamps remain intact.

## 11. Dynamic Heat Requirements

Dynamic Heat shall be computed from:

- `open_count`
- `archive_count`
- Time since `last_opened_at`
- Time since `last_seen_at`

The initial implementation may map a continuous score to display levels such as High, Medium, Low, and Cold.

The exact weights shall be configurable or isolated in one backend policy component so they can be tuned without changing persisted data.

The Eternal flag shall not overwrite the heat value. Eternal records shall instead:

- Receive a search-ranking boost.
- Be excluded from cleanup recommendations.
- Display a dedicated permanent marker.

## 12. Search Requirements

## 12.1 Keyword Search

Keyword search shall work without an embedding model and shall search at least:

- Title
- Comment
- Domain
- URL
- Labels

## 12.2 Structured Filters

Search shall support filters for:

- Scope: Live, Archive, or All
- Labels
- Domain
- Eternal state
- Health status
- Dynamic Heat level

## 12.3 Semantic Search

Semantic search shall use local embeddings and remain optional.

The embedding source text shall include:

- Title
- Comment
- Domain
- Meaningful normalized path tokens
- Labels

The full raw URL and noisy tracking parameters should not dominate the embedding text.

The implementation should reuse the Knowledge Vault embedding approach:

- Lazy model loading.
- Local model cache.
- Offline model use after installation.
- Normalized embeddings.
- SQLite vector persistence.
- Content-hash-based reindexing.

It shall not reuse Knowledge Vault fragment, node, or edge tables.

## 12.4 Hybrid Ranking

Search relevance should combine:

- Semantic similarity
- Keyword relevance
- Dynamic Heat
- Recency
- Eternal boost

The ranking policy shall be implemented as a replaceable backend component. Exact weights are implementation defaults and may be adjusted after real usage data is available.

## 12.5 Search Degradation

If the embedding model is unavailable, misconfigured, or still loading:

- Archive and restore operations shall continue to work.
- Keyword search and structured filters shall continue to work.
- The UI shall indicate that semantic search is unavailable.
- The request shall not fail solely because semantic indexing is unavailable.

## 13. Comment and Label Requirements

Users shall be able to:

- Add and edit a free-text comment.
- Create labels.
- Attach multiple labels to one archived tab.
- Remove labels from a tab without deleting the tab.
- Filter and search by labels.
- Toggle Eternal independently from labels and heat.

Changing title, comment, labels, domain-derived search content, or normalized path tokens shall mark the semantic index as stale and schedule asynchronous reindexing.

The archive operation shall not wait for embedding generation to complete.

## 14. Link Health Requirements

Supported health states shall include:

- `unchecked`
- `healthy`
- `redirected`
- `auth_required`
- `broken`
- `timeout`

Health checking shall:

- Be opt-in rather than automatically scanning every URL.
- Support a single-record check.
- Support a selected-record batch check.
- Use bounded concurrency and configurable timeouts.
- Avoid recording response bodies.
- Try a limited GET when HEAD is unsupported or inconclusive.
- Treat authentication-required responses separately from broken links.
- Record the final URL after redirects without automatically overwriting the stored original URL.
- Never delete a record automatically because a health check failed.

## 15. Browser Extension Requirements

The extension shall retain existing capabilities and add an `open_tabs` command.

The command shall accept:

- A list of record identifiers and URLs.
- Destination mode: new window or current window.

It shall return per-item results containing:

- Record identifier
- Success state
- Created or focused browser tab identifier when available
- Error information when unsuccessful

The extension shall also support detecting or focusing an already-open normalized URL as part of restore behavior.

The existing close operation shall return enough information to distinguish successfully closed tabs from failed tabs during archive operations.

## 16. Backend API Requirements

The Browser Agent backend shall add APIs for at least:

- Listing synchronized Live and Archive records.
- Archiving selected live tabs.
- Previewing an end-of-day archive operation.
- Executing an end-of-day archive operation.
- Restoring selected archived records.
- Reading and updating archived record metadata.
- Deleting an archived record explicitly.
- Creating, listing, and deleting labels.
- Attaching and removing labels.
- Keyword and hybrid search.
- Rebuilding stale semantic indexes.
- Checking link health for one or multiple records.
- Reading archive batch history.

All multi-step archive and restore APIs shall return item-level success and failure results.

## 17. Consistency and Failure Handling

The feature shall follow these guarantees:

1. Persist before close.
2. Count only confirmed operations.
3. Never delete archive data automatically after an extension timeout.
4. Reconcile Live status from the extension instead of trusting a stale database Boolean.
5. Preserve failed restore selections.
6. Make repeated archive requests idempotent by normalized URL where practical.
7. Avoid logging full URLs, comments, labels, or page titles in normal application logs.
8. Report partial success explicitly.

If the browser extension is unavailable:

- Archived data and search shall remain accessible.
- Live synchronization, archive-and-close, and restore shall return an actionable availability error.

## 18. Privacy and Security Requirements

- Archive data remains local in the Browser Agent SQLite database.
- The database and runtime settings shall remain excluded from version control.
- No user URL, title, comment, label, cookie, personal path, credential, or browsing history shall be hardcoded in source code.
- Semantic search shall use local embeddings by default.
- AI-assisted classification shall not be enabled by default.
- Health checks shall be user-initiated and clearly communicate that they make outbound requests.
- The feature shall not request or store cookies for archive/search behavior.
- Browser internal URLs and unsupported schemes shall not be archived or reopened automatically.

## 19. Performance Requirements

- Listing and keyword search should remain responsive for at least several thousand archived records.
- Semantic indexing shall run asynchronously.
- The embedding model shall load lazily and shall not delay application startup.
- Batch archive, restore, and health-check operations shall use bounded concurrency.
- The UI shall support pagination or virtualization for large result sets.
- Search shall debounce user input and cancel or ignore stale responses.

## 20. Implementation Phases

### Phase 1 — Reliable Archive Foundation

- Add archive-specific entities and self-healing SQLite schema.
- Add URL normalization and merge behavior.
- Add archive CRUD APIs.
- Add extension `open_tabs` support.
- Implement transactional persist-before-close behavior.
- Implement restore result accounting.
- Implement Live/Archive reconciliation.

### Phase 2 — Tabs User Interface

- Replace the current simple list with Live and Archive areas.
- Add compact record presentation and a details drawer.
- Add the Selection Basket.
- Add selected archive and safe end-of-day archive actions.
- Add restore destination choice.
- Add comment, labels, Eternal, heat, counters, and timestamps to details.

### Phase 3 — Search and Metadata

- Add robust keyword search and structured filters.
- Add label CRUD and assignment.
- Add Dynamic Heat calculation and sorting.
- Add archive batch history.

### Phase 4 — Semantic Search

- Extract or reuse a shared local embedding loader.
- Add asynchronous tab indexing.
- Add hybrid ranking and graceful degradation.
- Add stale-index rebuild support.

### Phase 5 — Link Health and Maintenance

- Add single and batch health checks.
- Add unavailable and redirected link views.
- Add non-destructive maintenance recommendations.
- Add local export, import, and backup support.

## 21. Acceptance Criteria

The feature is accepted when all applicable criteria below pass:

1. A selected live tab is persisted before it is closed.
2. A persistence failure leaves the corresponding live tab open.
3. Repeated archive operations for the same normalized URL do not create duplicate records.
4. Existing comments, labels, and Eternal state survive repeated archive operations.
5. Pinned tabs, Browser Agent pages, browser internal pages, and excluded patterns are omitted from the default end-of-day archive operation.
6. The end-of-day operation presents a preview and requires confirmation.
7. Selections survive multiple searches and filter changes.
8. Restore defaults to one new window and can target the current window.
9. Already-open URLs are focused instead of duplicated by default.
10. Only successfully restored or focused records increase `open_count` and update `last_opened_at`.
11. Only successfully archived and closed records increase `archive_count` and update `last_archived_at`.
12. Failed restore records remain archived and selected.
13. Keyword search works without an embedding model.
14. Comment and label changes become searchable and trigger semantic reindexing when semantic search is enabled.
15. Eternal records remain independent from Dynamic Heat and are excluded from cleanup recommendations.
16. Health-check failures do not delete or overwrite archive records.
17. Full URLs, comments, and labels are not emitted into normal application logs.
18. Browser Agent runtime settings and SQLite data remain ignored by Git.
19. Frontend type checking and production build pass.
20. Backend archive, restore, merge, reconciliation, search fallback, and partial-failure paths have automated tests.

## 22. Open Future Enhancements

The following ideas are intentionally deferred but compatible with this design:

- Restore tabs into their original window groups.
- Synchronize archives across devices.
- Native browser bookmark import and export.
- Automatic label suggestions.
- Page-summary generation with explicit user consent.
- Duplicate-content detection across different URLs.
- User-defined heat formulas and retention policies.
- Optional periodic health checks with strict rate limits.
