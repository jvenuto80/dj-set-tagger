# DJ Set Tagger

A Docker application for scanning and tagging DJ sets and electronic music tracks using metadata from 1001Tracklists.com. Perfect for organizing long DJ sets, podcasts, and radio show recordings.

![DJ Set Tagger Screenshot](docs/screenshot.png)

## Features

- 🎵 **Automatic Scanning**: Scans directories for audio files (MP3, FLAC, WAV, M4A, AAC, OGG)
- 🔍 **Fuzzy Matching**: Uses intelligent fuzzy string matching to find potential track matches on 1001Tracklists
- 📝 **Metadata Tagging**: Automatically tags tracks with artist, title, genre, and more
- 🖼️ **Cover Art Download**: Downloads and embeds cover art from matched tracklists
- 👁️ **Web Interface**: Modern dark-themed UI to review matches and make corrections
- 📦 **Batch Operations**: Process multiple tracks at once or one at a time
- ✏️ **Manual Editing**: Edit metadata manually when automatic matching isn't accurate
- 📁 **Smart Renaming**: Batch rename files using customizable patterns
- 🤖 **AI-Ready**: Architecture prepared for future AI-based matching (audio fingerprinting, etc.)

## Screenshots

### Dashboard
Overview of your library with quick stats and recent tracks.

### Track List
Browse all scanned tracks with filtering and batch actions.

### Track Detail
View match candidates, select the best match, and apply tags.

## Installation on Unraid

### Method 1: Using Docker Compose (Recommended)

1. SSH into your Unraid server or use the terminal

2. Create the app directory:
   ```bash
   mkdir -p /mnt/user/appdata/dj-set-tagger
   cd /mnt/user/appdata/dj-set-tagger
   ```

3. Download the project (or git clone):
   ```bash
   git clone https://github.com/yourusername/dj-set-tagger.git .
   ```

4. Edit `docker-compose.yml` to set your music path:
   ```yaml
   volumes:
     - ./config:/config
     - /mnt/user/media/music/dj-sets:/music  # Change this to your path
   ```

5. Build and start:
   ```bash
   docker-compose up -d --build
   ```

6. Access the web UI at `http://your-unraid-ip:8080`

### Method 2: Using Unraid Docker Template

1. In Unraid, go to **Docker** tab
2. Click **Add Container**
3. Use these settings:
   - **Name**: `dj-set-tagger`
   - **Repository**: Build locally or use `ghcr.io/yourusername/dj-set-tagger:latest`
   - **Network Type**: `Bridge`
   
4. Add port mappings:
   - `8080` -> `8080` (Web UI)
   - `5000` -> `5000` (API)

5. Add path mappings:
   - `/music` -> Your DJ sets folder (e.g., `/mnt/user/media/music/dj-sets`)
   - `/config` -> `/mnt/user/appdata/dj-set-tagger`

6. Click **Apply**

### Method 3: Manual Docker Run

```bash
# Build the image
cd /mnt/user/appdata/dj-set-tagger
docker build -t dj-set-tagger .

# Run the container
docker run -d \
  --name dj-set-tagger \
  --restart unless-stopped \
  -p 8080:8080 \
  -p 5000:5000 \
  -v /mnt/user/media/music/dj-sets:/music \
  -v /mnt/user/appdata/dj-set-tagger/config:/config \
  -e TZ=America/New_York \
  dj-set-tagger
```

## Usage Guide

### 1. Initial Setup
1. Open the web UI at `http://your-server:8080`
2. Go to **Settings** and verify your music directory path
3. Adjust the fuzzy matching threshold if needed (default: 70%)

### 2. Scan Your Library
1. Go to **Scan** page
2. Click **Start Scan**
3. Wait for the scan to complete (progress shown in real-time)

### 3. Review Matches
1. Go to **Tracks** page
2. Click on a track to see match candidates
3. Review the suggested matches from 1001Tracklists
4. Click on the best match to select it

### 4. Apply Tags
1. Once a match is selected, click **Apply Tags to File**
2. The track's metadata (title, artist, genre) and cover art will be written to the file
3. Use batch operations to process multiple tracks at once

### 5. Batch Operations
- **Match All Pending**: Automatically search for matches for all unmatched tracks
- **Tag All Matched**: Apply tags to all tracks that have been matched
- **Batch Rename**: Rename files using a pattern like `{artist} - {title}`

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MUSIC_DIR` | `/music` | Directory to scan for audio files |
| `CONFIG_DIR` | `/config` | Directory for database and settings |
| `SCAN_EXTENSIONS` | `mp3,flac,wav,m4a,aac,ogg` | File extensions to scan |
| `TZ` | `UTC` | Timezone |

### Settings (via Web UI)

- **Music Directory**: Path to your audio files
- **File Extensions**: Which file types to scan
- **Fuzzy Threshold**: Minimum match confidence (0-100)
- **Request Delay**: Delay between 1001Tracklists requests (to avoid rate limiting)

## Architecture

```
dj-set-tagger/
├── backend/                 # FastAPI Python backend
│   ├── api/                 # REST API routes
│   │   ├── tracks.py        # Track CRUD operations
│   │   ├── scan.py          # Directory scanning
│   │   ├── match.py         # 1001Tracklists matching
│   │   ├── tags.py          # Metadata tagging
│   │   └── settings.py      # App configuration
│   ├── services/            # Business logic
│   │   ├── scanner.py       # File scanning service
│   │   ├── matcher.py       # Fuzzy matching engine
│   │   ├── tagger.py        # Audio file tagging
│   │   ├── tracklists_api.py # 1001Tracklists scraper
│   │   └── database.py      # SQLite database
│   ├── models/              # SQLAlchemy & Pydantic models
│   │   └── track.py         # Track data models
│   └── main.py              # FastAPI application
├── frontend/                # React + Vite frontend
│   ├── src/
│   │   ├── components/      # Reusable components
│   │   ├── pages/           # Page components
│   │   └── api.js           # API client
│   └── package.json
├── docker/                  # Docker configuration
│   └── start.sh             # Container startup script
├── unraid/                  # Unraid-specific files
│   └── dj-set-tagger.xml    # Unraid template
├── Dockerfile               # Production Docker build
├── docker-compose.yml       # Docker Compose config
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/tracks` | List all tracks |
| GET | `/api/tracks/{id}` | Get track details |
| PATCH | `/api/tracks/{id}` | Update track metadata |
| POST | `/api/scan/start` | Start directory scan |
| GET | `/api/scan/status` | Get scan progress |
| POST | `/api/match/{id}` | Find matches for track |
| POST | `/api/match/batch` | Batch match tracks |
| POST | `/api/tags/{id}/apply` | Apply tags to file |
| GET | `/api/settings` | Get settings |
| PATCH | `/api/settings` | Update settings |

## Troubleshooting

### No matches found
- Check that the filename contains the DJ/artist name
- Try manually searching on 1001Tracklists to verify the set exists
- Lower the fuzzy threshold in Settings

### Rate limiting (403 errors)
- Increase the request delay in Settings
- Wait a few minutes before retrying

### Tags not saving
- Ensure the container has write permissions to the music directory
- Check that the file format is supported (MP3, FLAC, M4A, OGG)

### Scan not finding files
- Verify the path mapping in Docker
- Check that the file extensions are in the scan list

## Future Enhancements

- [ ] Audio fingerprinting (AcoustID/Shazam-style matching)
- [ ] AI-powered metadata extraction
- [ ] Spotify/Beatport integration
- [ ] Cue file generation
- [ ] Waveform visualization
- [ ] Mobile-responsive UI improvements

## Credits

- [1001-tracklists-api](https://github.com/jvenuto80/1001-tracklists-api) - Inspiration and reference for 1001Tracklists scraping
- [Mutagen](https://mutagen.readthedocs.io/) - Python audio metadata handling
- [RapidFuzz](https://github.com/maxbachmann/RapidFuzz) - Fast fuzzy string matching
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [React](https://react.dev/) - Frontend framework
- [Tailwind CSS](https://tailwindcss.com/) - Styling

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please open an issue or PR on GitHub.
