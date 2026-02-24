# Pluggy - Production-Ready Torrent Manager

A feature-complete torrent search and download manager with RealDebrid integration.

## 🚀 Features

### Engine Layer

✅ **Concurrent Multi-Source Search**
- ThreadPoolExecutor-based concurrent searching across all enabled sources
- Searches complete as fast as the slowest source

✅ **Infohash-Based Deduplication**
- Automatic deduplication of identical torrents from different sources
- Keeps result with highest seed count

✅ **Size Normalization**
- Handles various size formats: GB, GiB, MB, MiB, etc.
- Consistent byte-based storage and filtering

✅ **Intelligent Seed Sorting**
- Results sorted by seed count (descending)
- Secondary sort by file size for quality preference

✅ **In-Memory LRU Cache**
- Search results cached with 5-minute TTL
- Maximum 100 queries cached
- Automatic eviction of oldest entries

✅ **Source Enable/Disable**
- Runtime source configuration
- Hot reload without restart

✅ **Event-Driven Architecture**
- Decoupled components via EventBus
- Real-time progress updates

### Download System

✅ **Max Concurrent Limit**
- Semaphore-based concurrency control
- Configurable concurrent download limit (1-10)

✅ **Pause Support**
- Pause downloads mid-transfer
- Threading event-based control

✅ **Resume Support**
- HTTP range requests for resuming partial downloads
- Automatic detection of existing partial files

✅ **Cancel Support**
- Instant cancellation via threading events
- Clean job state transitions

✅ **Speed Calculation**
- Real-time download speed in KB/s or MB/s
- Elapsed time and ETA estimation

✅ **Event-Driven Progress Updates**
- 500ms throttled progress events
- Prevents UI flooding

✅ **Qt Signal Bridge**
- Thread-safe UI updates via Qt signals
- EventBus to Qt signal translation

### RealDebrid Integration

✅ **Device OAuth Flow**
- Full OAuth device code flow
- User-friendly authorization process

✅ **Polling Thread**
- Background polling for device authorization
- Configurable poll interval

✅ **Token Persistence**
- Access and refresh tokens saved to settings
- Automatic persistence in user home directory

✅ **Auto Token Refresh**
- Automatic token refresh on 401 responses
- Transparent retry with new token

### UI Layer

✅ **Dark Theme**
- Professional dark theme optimized for long sessions
- Syntax-highlighted accents (VS Code inspired)

✅ **Search Tab**
- Clean search interface with instant results
- Background threading keeps UI responsive

✅ **Pagination Controls**
- Previous/Next navigation
- Page indicator
- Configurable results per page

✅ **Filter Controls**
- **Min Seeds Slider**: Filter by minimum seed count (0-50)
- **Size Range Filter**: Min/Max size in GB (0-999)
- **Source Dropdown**: Select which sources to search

✅ **Column Sorting**
- Click column headers to sort results
- Sort by title, source, size, seeds, or leeches

✅ **Reactive Download Tab**
- Real-time progress bars
- Speed and ETA display
- Live status updates

✅ **Per-Job Cancel Buttons**
- Individual pause/cancel controls
- Instant feedback

✅ **Persistent Settings Dialog**
- Download folder picker
- Max concurrent downloads
- Source enable/disable checkboxes
- RealDebrid authentication

✅ **Hot Reload**
- Apply source changes without restart
- Instant filter updates

### Cross-Platform

✅ **Safe Filenames**
- Automatic sanitization of invalid characters
- Handles Windows reserved names (CON, PRN, etc.)
- Removes problematic characters: `< > : " / \ | ? *`

✅ **Pathlib Usage**
- Modern path handling throughout
- Cross-platform compatibility

✅ **Settings in User Home**
- Settings stored in `~/.pluggy/settings.json`
- Automatic directory creation
- Portable configuration

✅ **PyInstaller Compatible**
- Clean imports and resource handling
- Ready for single-file executable creation

## 📦 Installation

```bash
# Clone or extract
cd pluggy

# Install dependencies
pip install -r requirements.txt
```

## 🎯 Usage

```bash
# Run the application
python -m pluggy.main
```

Or directly:
```bash
python pluggy/main.py
```

## 🏗️ Architecture

```
pluggy/
├── main.py                     # Application entry point
├── core/                       # Core engine layer
│   ├── event_bus.py           # Event dispatching system
│   ├── settings_manager.py    # Settings persistence
│   ├── source_manager.py      # Multi-source search engine
│   └── download_manager.py    # Download queue manager
├── models/                     # Data models
│   ├── search_result.py       # Search result with deduplication
│   └── download_job.py        # Download job state
├── services/                   # External service integrations
│   └── realdebrid_client.py   # RealDebrid API client
├── sources/                    # Search source plugins
│   ├── piratebay.py           # PirateBay source
│   └── x1337.py               # 1337x source
├── ui/                         # Qt-based UI
│   ├── main_window.py         # Main window with tabs
│   └── qt_bridge.py           # EventBus to Qt signals
└── utils/                      # Utility functions
    └── file_utils.py          # Cross-platform file operations
```

## ⚙️ Configuration

Settings are stored in `~/.pluggy/settings.json`:

```json
{
  "pagination_size": 20,
  "min_seeds": 0,
  "size_min_gb": 0.0,
  "size_max_gb": 100.0,
  "enabled_sources": {
    "PirateBay": true,
    "1337x": true
  },
  "download_folder": "/home/user/Downloads/Pluggy",
  "max_concurrent_downloads": 3,
  "rd_access_token": "",
  "rd_refresh_token": "",
  "dark_theme": true
}
```

## 🔧 RealDebrid Setup

1. Click **Settings** tab
2. Click **Authorize Device**
3. Visit the displayed URL
4. Enter the code shown
5. Wait for confirmation
6. Tokens are automatically saved

## 🎨 UI Features

### Search Tab
- Enter query and press Enter or click Search
- Adjust filters before searching
- Results auto-deduplicate by infohash
- Click column headers to sort
- Click Download to queue

### Downloads Tab
- View all active/completed downloads
- Real-time progress bars
- Speed and ETA calculations
- Pause/Cancel individual downloads

### Settings Tab
- Change download folder
- Adjust concurrent download limit
- Enable/disable search sources
- RealDebrid authentication

## 🚦 Event System

The application uses an event-driven architecture:

```
EventBus → QtBridge → UI Updates
    ↓
Components subscribe/emit events
```

Key events:
- `SEARCH_STARTED/COMPLETED/PROGRESS`
- `DOWNLOAD_QUEUED/STARTED/PROGRESS/COMPLETED/CANCELLED`
- `RD_AUTH_PENDING/SUCCESS/FAILED`
- `SOURCES_RELOADED`

## 📊 Performance

- **Search**: Concurrent across all sources (typically 2-5 seconds)
- **Deduplication**: O(n) hash-based deduplication
- **Cache**: LRU cache reduces repeat searches to instant
- **Downloads**: HTTP range requests for resume support
- **UI**: Background threading keeps interface responsive

## 🛡️ Error Handling

- Failed searches return empty results (no crash)
- Download errors emit error events
- Network timeouts handled gracefully
- Token refresh automatic on 401

## 🔐 Security

- OAuth tokens encrypted in settings file
- No passwords stored
- HTTPS for all API calls
- User consent required for device auth

## 📝 Adding Sources

Create a new source in `sources/`:

```python
from typing import List
from models.search_result import SearchResult

class MySource:
    name = "MySource"
    
    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        # Implement search logic
        return results
```

Register in `main.py`:
```python
source_manager.register(MySource())
```

## 🐛 Known Limitations

- 1337x source requires fetching detail page for magnet (slower)
- Cache doesn't persist between sessions
- No torrent client integration (RealDebrid only)
- Maximum 999 GB size filter

## 📄 License

MIT License - Free to use and modify

## 🙏 Credits

Built with:
- PySide6 for Qt UI
- Requests for HTTP
- BeautifulSoup4 for parsing
- RealDebrid API for premium links

---

**Made with ❤️ for the community**
