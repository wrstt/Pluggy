# Pluggy - Quick Start Guide

## 🚀 5-Minute Setup

### Step 1: Install Dependencies

```bash
cd pluggy
pip install -r requirements.txt
```

**Requirements:**
- Python 3.8+
- pip

### Step 2: Run Pluggy

```bash
python main.py
```

Or:
```bash
python -m pluggy.main
```

The application will start with the dark theme enabled!

## 🎯 First Time Use

### Configure Download Folder

1. Click the **Settings** tab
2. Click **Choose Folder** under "Download Folder"
3. Select your preferred download location
4. Click **Save Settings**

### Setup RealDebrid (Optional)

1. Go to **Settings** tab
2. Click **Authorize Device**
3. A dialog will appear with:
   - Verification URL (e.g., https://real-debrid.com/device)
   - User code (e.g., A9B2C3)
4. Visit the URL in your browser
5. Enter the code
6. Wait for authorization (dialog will close automatically)
7. Done! Tokens are saved

## 🔍 First Search

### Basic Search

1. Click **Search** tab
2. Type your query (e.g., "ubuntu iso")
3. Press **Enter** or click **Search**
4. Results appear in 2-5 seconds

### Using Filters

**Before searching**, adjust filters:

- **Min Seeds**: Slide to filter low-seed torrents
- **Size Range**: Set min/max file size in GB
- **Sources**: Uncheck sources you don't want

Then search!

### Sorting Results

Click any column header:
- **Title**: Alphabetical
- **Source**: Group by source
- **Size**: Smallest/largest first
- **Seeds**: Most/least seeded
- **Leeches**: Active downloaders

### Pagination

- **Next →**: Go to next page
- **← Previous**: Go back
- Page number shows current page

## 📥 Downloading

### Start Download

1. Find a torrent in search results
2. Click **Download** button in Actions column
3. Automatically switches to **Downloads** tab
4. Download starts immediately

### Monitor Progress

In **Downloads** tab:
- **Progress bar**: Visual completion
- **Speed**: Current download speed
- **Status**: queued, resolving, downloading, paused, completed
- **Size**: Downloaded / Total

### Control Downloads

Each download has:
- **Pause**: Stop temporarily
- **Cancel**: Stop permanently

## ⚙️ Settings

### Max Concurrent Downloads

Control how many files download at once:
1. Settings tab
2. Change "Max Concurrent Downloads" (1-10)
3. Click **Save Settings**

### Enable/Disable Sources

Turn search sources on/off:
1. Settings tab → Search Sources
2. Check/uncheck sources
3. Click **Apply & Reload Sources**
4. No restart needed!

## 🎨 UI Tips

### Dark Theme

The dark theme is on by default. It's optimized for:
- Long viewing sessions
- Low-light environments
- Professional appearance

### Keyboard Shortcuts

- **Enter** in search box → Start search
- **Ctrl+W** → Close window (saves settings)

### Window Size

Your window size is automatically saved when you close the app!

## 🔧 Troubleshooting

### No Search Results

- Check your internet connection
- Try a different query
- Enable more sources in Settings
- Lower the min seeds filter

### Download Not Starting

- Verify RealDebrid is authenticated
- Check download folder is writable
- Ensure magnet link is valid

### Slow Searches

- Disable sources you don't need
- 1337x is slower (fetches detail pages)
- PirateBay is typically faster

### Settings Not Saving

- Check `~/.pluggy/` folder exists
- Ensure you have write permissions
- Click **Save Settings** button

## 📂 File Locations

### Settings File
```
~/.pluggy/settings.json
```

### Download Folder
Default:
```
~/Downloads/Pluggy/
```

You can change this in Settings!

## 🎓 Advanced Usage

### Custom Download Location Per File

Currently, all downloads go to the configured folder. To change location:
1. Settings → Choose Folder
2. Save Settings
3. New downloads will use new location

### Search Multiple Sources Simultaneously

All enabled sources are searched concurrently! Just check the sources you want in filters.

### Resume Interrupted Downloads

If a download is interrupted:
1. The file is saved partially
2. Next time you download the same file
3. It will resume from where it left off!

## 🎉 You're Ready!

Now you know how to:
- ✅ Search torrents
- ✅ Apply filters
- ✅ Download files
- ✅ Control downloads
- ✅ Configure settings
- ✅ Use RealDebrid

Happy downloading! 🚀
