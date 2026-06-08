# Changelog

All notable changes to SetList will be documented in this file.

## [1.3.0-beta] - 2026-06-07

### Added
- **Bulk tag popup on the Tracks page** — the **Tag Selected** button now opens
  a modal to edit Title, Artist, Album, Album Artist, Genre, and Year across all
  selected tracks in one action.
  - Shared values are prefilled when every selected track agrees on a field.
  - Per-field **Clear** toggles remove a tag across the whole selection.
  - **Apply existing matched tags only** checkbox writes current matched
    metadata to files without changing any fields.
  - A success toast confirms when bulk tagging has started.

### Changed
- App version bumped to **1.3.0-beta** across `backend/main.py`,
  `frontend/package.json`, `tauri.conf.json`, and `Cargo.toml`.

## [1.2.0-beta] - 2026-05-24

### Added
- **Bulk FLAC/WAV → MP3 conversion in the UI**
  - Library Scan page: **Convert All Non-MP3 Tracks** button (one-click bulk).
  - Tracks page: bulk-action **Convert to MP3** button on selected rows.
  - Backend `POST /api/library/convert/to-mp3` accepts `track_ids: null` to convert
    every non-MP3 in the library.
- **File-format filter on the Tracks page** — dropdown populated dynamically
  from `GET /api/tracks/filters` (`formats` field). Filter by `.mp3`, `.flac`,
  `.wav`, etc. to scope bulk actions to a single format.
- **`ffmpeg` absolute-path resolver** (`FFMPEG_BIN`) — mirrors the `fpcalc`
  resolver so conversion works inside the sandboxed Tauri sidecar where the
  GUI process has a stripped `PATH`.
- Cover-art "Cache-Control" headers (added in 1.1, hardened here) — embedded
  cover responses cached privately for one hour to avoid refetching while
  scrolling lists.

### Changed
- **Conversion checkbox label is now stable** — "Delete originals after
  conversion" no longer swaps between "Keep originals" / "Delete originals"
  based on state. Unchecked = keep (safe default). Checked = label turns red
  with a ⚠ glyph to telegraph the destructive action.
- **Track row is updated in the database after a replace-conversion** —
  `filepath`, `filename`, `file_format`, and `file_size` now reflect the new
  `.mp3` file; stale `fingerprint_hash` / `fingerprint_raw` are cleared so
  the next AcoustID run regenerates the fingerprint against the new file.
- Convert / Tracks mutations now invalidate the `['tracks']`,
  `['track-stats']`, and `['track-filters']` React Query caches on success
  so the UI reflects new MP3s without a manual refresh.
- App version bumped to **1.2.0-beta** across `backend/main.py`,
  `frontend/package.json`, `tauri.conf.json`, and `Cargo.toml`.

### Fixed
- **`batch_convert_to_mp3`, `run_library_scan`, and the filesystem scan loop
  now always clear their `running` flag**, even if the underlying job
  crashes. Previously a single exception inside any of these long-running
  background jobs left `running=True` forever, blocking the user from
  starting a new scan or conversion until the app was restarted.
- **Scanner indentation regression** — a misindented `for` loop inside
  `async with get_db()` raised `IndentationError` on import, preventing the
  FastAPI backend from starting at all (UI showed "Network error" on the
  Series tab and an empty Tracks list).
- Identify-Audio / AcoustID error path now logs the underlying exception
  instead of swallowing it.

### Removed
- Last references to the old "coming soon" placeholder text in the
  conversion UI.

---

## [1.1.0-beta] - 2026-05-24

### Added
- **Embedded cover art fallback** — track list and detail views now display
  the cover image embedded in the audio file (APIC / FLAC picture / MP4 covr
  / OGG metadata_block_picture) when no matched cover URL is available.
- New `TrackCover` component with three-tier fallback (matched URL →
  embedded art → music-note icon).
- `Cache-Control: private, max-age=3600` on embedded cover responses to
  avoid refetching on every render.

### Changed
- **Native-only build** — removed Docker / Unraid support entirely. App now
  ships as a Tauri desktop bundle (`SetList.app`) only.
  - Deleted `Dockerfile`, `Dockerfile.dev`, `docker-compose*.yml`,
    `.dockerignore`, `docker/`, `unraid/`.
  - Default paths now point at `~/Music` and `~/.setlist` (was `/host`,
    `/config`).
  - Settings directory browser no longer prepends `/host`; paths are shown
    and stored as-is.
  - CORS defaults restricted to loopback + Tauri webview origins.
  - `/api/health` always reports `native: true`.
- `scripts/dev-macos.sh` binds to `127.0.0.1:5050` (was `0.0.0.0:5000`) to
  match the production port and avoid network exposure.
- `scripts/build-macos.sh` deploy step now `rm -rf`s the target `.app`
  before copying to prevent stale Python files being preserved by a merge.

### Fixed
- AcoustID Identify Audio works again — uses bundled `fpcalc` via an
  absolute path so it works inside the Tauri sidecar environment.
- Audio streaming works inside the bundled app — added
  `media-src 'self' http://127.0.0.1:5050 blob:` to the Tauri CSP.
- Two bare `except:` clauses replaced with scoped exceptions and debug
  logging (`scanner.py`, `tracklists_api.py`).

### Removed
- Stale Docker-era `config/` directory (logs, dev DBs, settings.json with
  an exposed API key). Runtime state now lives exclusively under
  `~/.setlist/`.

---

## [1.0.0-beta] - 2024-12-23

### Added
- **Duplicate Detection Page** - New dedicated page for finding and managing duplicate audio files
  - Audio fingerprint generation using Chromaprint/fpcalc
  - Waveform visualization for comparing duplicates
  - Side-by-side audio playback comparison
  - Safe file deletion with confirmation modal
  
- **Parallel Fingerprint Generation** - Dramatically faster fingerprint processing
  - Configurable worker count (1-16 parallel processes)
  - Default 8 workers, recommended 4-8 for most systems, 12-16 for high-end machines
  - Real-time progress tracking with floating progress bar
  - Stop button to cancel generation at any time
  
- **Fingerprint Status Display**
  - Shows fingerprinted vs unfingerprinted track counts
  - Option to regenerate all fingerprints or only process new tracks
  
- **Git Release Workflow**
  - Main branch for stable releases
  - Develop branch for ongoing development

### Changed
- Moved fingerprint generation UI from Settings to Duplicates page
- Updated AcoustID instructions in Settings page
- Improved polling behavior - only polls during active generation

### Technical
- AsyncIO semaphore-based parallel processing for fpcalc
- Global state management for fingerprint generation progress
- Cancellation mechanism with graceful shutdown
- React Query optimized polling intervals

---

## [0.9.0-beta] - Initial Release

### Features
- Track scanning and metadata extraction
- Series/DJ set organization
- Tracklist matching via 1001tracklists API
- Tag editing and management
- AcoustID integration for track identification
- Dashboard with library statistics
