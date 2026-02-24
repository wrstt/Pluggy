# Automated Torrent Search - How It Works

## The Problem: Manual Browsing is Painful

### What users do manually on PirateBay/1337x:
1. **Navigate to site** → Deal with ads, popups, redirects
2. **Type search query** → More ads appear
3. **Browse results page** → Ads everywhere, fake download buttons
4. **Click on torrent** → New tab opens with more ads
5. **Find real download link** → Surrounded by fake "Download" buttons
6. **Click magnet link** → Final popup ads
7. **Close popup windows** → 3-5 popup windows to close
8. **Finally start download** → If you didn't click a fake link

**Time spent:** 30-60 seconds per torrent (mostly dealing with ads)
**Frustration level:** Maximum

## Our Solution: Pure HTTP Scraping (Zero Ads)

### What Pluggy does automatically:
1. **Direct HTTP request** → No browser = no JavaScript = no ads
2. **Parse HTML** → Extract torrent data from page structure
3. **Get magnet links** → Direct extraction, no clicking
4. **Sort & rank** → Best results first (by seeds, version, quality)
5. **Display clean list** → No ads, just data
6. **One-click download** → Straight to RealDebrid

**Time spent:** 2-5 seconds for entire search
**Frustration level:** Zero
**Ads seen:** Zero

## How It Works: Technical Deep Dive

### Phase 1: Search Request (Ad-Free)

```python
# What the user sees: Enter "photoshop" in search box
# What Pluggy does behind the scenes:

# 1. Build search URL
url = "https://1337x.to/search/photoshop/1/"

# 2. Send HTTP request (no browser, no JavaScript, no ads)
response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0...'})

# 3. Get raw HTML
html = response.content
# This is pure HTML text - no ads can execute!
```

**Key insight:** By using `requests` instead of a browser, we skip ALL JavaScript-based ads. The ads literally cannot run.

### Phase 2: Parse Results (Extract Data)

```python
# Parse the HTML table structure
soup = BeautifulSoup(html, 'html.parser')

# Find torrent listings
for row in soup.select('.table-list tbody tr'):
    # Extract data from each row
    title = row.select_one('.name a').get_text()
    seeds = int(row.select_one('.seeds').get_text())
    size = row.select_one('.size').get_text()
    
    # Get detail page URL
    detail_url = row.select_one('.name a')['href']
```

This mimics looking at the search results table, but programmatically.

### Phase 3: Get Magnet Links (No Popups)

**Method A: PirateBay (Magnet in Search Results)**
```python
# PirateBay puts magnets directly in search results - easy!
magnet = row.select_one('a[href^="magnet:"]')['href']
# Done! No need to visit detail page
```

**Method B: 1337x (Need Detail Page)**
```python
# 1337x requires visiting detail page for magnet
detail_response = requests.get(detail_url)
detail_soup = BeautifulSoup(detail_response.content, 'html.parser')

# Find magnet link on detail page
magnet = detail_soup.select_one('a[href^="magnet:"]')['href']
# Still no popups - it's pure HTTP!
```

### Phase 4: Smart Sorting (Best First)

Our enhanced sorting algorithm:

```python
def sort_results(results):
    for result in results:
        # 1. Extract version number
        version = extract_version(result.title)
        # "Photoshop 2024" → version = 2024
        # "Photoshop v25.0" → version = 25.0
        
        # 2. Check quality indicators
        quality_score = 0
        if 'repack' in title: quality_score += 10
        if 'proper' in title: quality_score += 10
        if '1080p' in title: quality_score += 5
        
        # 3. Calculate sort key
        sort_key = (
            -seeds,           # Most important: availability
            -version,         # Newer versions first
            -size,           # Larger = better quality
            -quality_score   # Quality indicators
        )
    
    return sorted(results, key=sort_key)
```

**Result:**
- "Adobe Photoshop 2024 v25.0 (50 seeds, 2.1 GB)"
- "Adobe Photoshop 2023 v24.0 (120 seeds, 2.0 GB)"
- "Adobe Photoshop CC 2022 (80 seeds, 1.9 GB)"

Best version with good seeds appears first!

### Phase 5: Deduplication (Same Torrent, Multiple Sources)

```python
# Same torrent on PirateBay AND 1337x?
# Identified by infohash (unique torrent identifier)

results_by_hash = {}
for result in all_results:
    hash = result.infohash
    
    if hash in results_by_hash:
        # Already have this torrent
        # Keep version with more seeds
        if result.seeds > results_by_hash[hash].seeds:
            results_by_hash[hash] = result
    else:
        results_by_hash[hash] = result

# Now we have unique torrents only!
```

## Mirror Support (Automatic Fallback)

Sites get blocked? We handle it:

```python
MIRRORS = [
    "https://1337x.to",      # Primary
    "https://1337x.st",      # Fallback 1
    "https://x1337x.ws",     # Fallback 2
    "https://x1337x.eu",     # Fallback 3
]

def search(query):
    for mirror in MIRRORS:
        try:
            return search_on_mirror(mirror, query)
        except:
            # This mirror is down, try next
            continue
```

If primary site is blocked, automatically tries mirrors until one works.

## HTTP Sources: Custom Sites

For sites like VST Torrents, Pluggy can scrape any site:

### Example: VST Torrents Workflow

1. **User configures URL:**
   ```
   https://vsttorrents.com/search?q={query}
   ```

2. **User searches "serum"**
   ```python
   # Pluggy substitutes query
   url = "https://vsttorrents.com/search?q=serum"
   
   # Fetches page
   response = requests.get(url)
   
   # Finds all magnet links
   magnets = soup.find_all('a', href=re.compile(r'^magnet:'))
   
   # Extracts metadata from surrounding text
   for magnet in magnets:
       title = magnet.parent.find('h2').text
       # "Serum VST v1.35b Win/Mac"
       
       size = magnet.parent.find('.size').text
       # "50 MB"
       
       seeds = estimate_seeds_from_comments()
       # Sites without seed counts: estimate from popularity
   ```

3. **Results appear** with all other sources
   ```
   ✓ Serum v1.35b (PirateBay - 45 seeds)
   ✓ Serum v1.35b (1337x - 38 seeds)
   ✓ Serum v1.35b (VSTTorrents - ~30 seeds)
   → Deduplicated to single result (45 seeds)
   ```

## Performance Optimizations

### 1. Concurrent Searching
```python
# Search all sources simultaneously, not one-by-one
with ThreadPoolExecutor(max_workers=10) as executor:
    piratebay_future = executor.submit(search_piratebay, query)
    x1337_future = executor.submit(search_1337x, query)
    http_future = executor.submit(search_http_sources, query)
    
    # Wait for all to complete
    all_results = []
    all_results += piratebay_future.result()
    all_results += x1337_future.result()
    all_results += http_future.result()
```

**Benefit:** 3 sources searched in ~3 seconds instead of 9 seconds

### 2. Result Caching
```python
cache = {
    "photoshop|page1|seeds:10": {
        "timestamp": 1705123456,
        "results": [...]
    }
}

def search(query, page):
    cache_key = f"{query}|page{page}|{filters}"
    
    if cache_key in cache:
        age = time.now() - cache[cache_key]['timestamp']
        if age < 300:  # 5 minutes
            return cache[cache_key]['results']  # Instant!
    
    # Not cached or expired, do real search
    results = do_search(query, page)
    cache[cache_key] = {'timestamp': time.now(), 'results': results}
    return results
```

**Benefit:** Repeat searches = instant (0 seconds)

### 3. Smart Pagination
```python
# Pre-fetch next page while user views current page
def display_results(page):
    show(get_results(page))
    
    # Background thread pre-fetches next page
    threading.Thread(target=prefetch, args=(page + 1,)).start()

def prefetch(page):
    get_results(page)  # Populates cache
```

**Benefit:** "Next Page" feels instant

## Integration with RealDebrid

Once user clicks "Download":

```python
def download_torrent(result):
    # 1. Send magnet to RealDebrid
    rd_client.add_magnet(result.magnet)
    
    # 2. RealDebrid processes torrent
    # - Checks cache (instant if cached)
    # - Downloads to their servers (fast, premium speeds)
    # - Makes available as direct download link
    
    # 3. Download manager starts download
    # - Direct HTTP download (no P2P)
    # - Full speed (RealDebrid premium)
    # - Secure connection
    
    # 4. File appears in Downloads tab
    # - Progress bar
    # - Speed indicator
    # - ETA
```

## Comparison: Manual vs Automated

### Manual Process (1337x with ads)
```
0s  → Navigate to 1337x.to
2s  → Close popup ad
4s  → Type "photoshop" in search
6s  → Wait for results (with ads loading)
8s  → Scroll past ads to find real results
10s → Click on torrent
12s → Close popup ad
14s → Navigate to new page with more ads
16s → Find real download button among fakes
18s → Click magnet link
20s → Close final popup
22s → Download starts

Total: 22 seconds, 5 popups closed, high frustration
```

### Automated Process (Pluggy)
```
0s → Type "photoshop" in search box
1s → Click "Search"
2s → HTTP requests sent to all sources
3s → Results parsing
4s → Sorting & deduplication
5s → Results displayed
6s → Click "Download" on best result
7s → Magnet sent to RealDebrid
8s → Download appears in Downloads tab

Total: 8 seconds, 0 popups, zero frustration
```

**Time saved:** 14 seconds per torrent
**Over 100 searches:** 23 minutes saved
**Ads avoided:** 500+ popups

## Why This Works Better

### 1. No Ads (Technical Impossibility)
- JavaScript ads can't run in `requests` library
- Only static HTML is retrieved
- Popup scripts never execute
- Tracking scripts never load

### 2. Faster Than Browser
- No rendering engine
- No CSS processing
- No JavaScript execution
- Pure data extraction

### 3. Better Organization
- Deduplication across sources
- Version-aware sorting
- Quality indicators
- Unified interface

### 4. More Reliable
- Automatic mirror fallback
- Error handling per source
- Partial results on failures
- Concurrent searches reduce total failure risk

## Adding New Sources

To add a new torrent site:

```python
class NewSiteSource:
    name = "NewSite"
    
    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        # 1. Build search URL
        url = f"https://newsite.com/search?q={query}&page={page}"
        
        # 2. Fetch HTML
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 3. Find torrent listings (adapt to site structure)
        for item in soup.select('.torrent-item'):
            title = item.select_one('.title').text
            magnet = item.select_one('a[href^="magnet:"]')['href']
            seeds = int(item.select_one('.seeds').text)
            
            yield SearchResult(
                title=title,
                magnet=magnet,
                seeds=seeds,
                # ... other fields
            )
```

Then register in `main.py`:
```python
source_manager.register(NewSiteSource())
```

Done! The new source now appears in search filters.

## Summary

**Manual browsing:** Slow, ad-filled, frustrating
**Pluggy automation:** Fast, ad-free, organized

**The magic:** Pure HTTP scraping eliminates the entire ad ecosystem. By avoiding browsers and JavaScript, we access the same data users see, but without any of the garbage surrounding it.

**Result:** Clean, fast, organized torrent search with multi-source concurrent queries, intelligent sorting, and seamless RealDebrid integration.

No ads. No popups. No frustration. Just search and download.
