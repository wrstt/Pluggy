# HTTP Sources - User Guide

## What Are HTTP Sources?

HTTP Sources let you add custom websites to Pluggy's search. Instead of just searching PirateBay and 1337x, you can search any website that lists torrents with magnet links.

## How It Works

1. You provide a URL template with `{query}` as a placeholder
2. When you search, Pluggy replaces `{query}` with your search term
3. Pluggy fetches the page and looks for magnet links
4. Any torrents found are added to your search results

## Setting Up HTTP Sources

### Step 1: Enable HTTP Sources
1. Open Pluggy
2. Go to **Settings** tab
3. Find the **"HTTP Sources"** section
4. Check ☑️ **"Enable HTTP Sources"**

### Step 2: Add URLs
1. Click **"Edit HTTP Sources"** button
2. In the dialog, click **"Add Row"**
3. Enter a URL template with `{query}`
4. Click **"Save"**

### Example URLs

#### Academic Torrents
```
https://academictorrents.com/browse.php?search={query}
```

#### Archive.org
```
https://archive.org/search.php?query={query}
```

#### Your Own Server
```
https://myserver.com/torrents?q={query}
```

### Step 3: Search
1. Go to **Search** tab
2. You'll see "HTTP" in the source checkboxes
3. Make sure ☑️ HTTP is checked
4. Search normally - results will include HTTP sources!

## URL Format Requirements

### Required Format
Your URL must include `{query}` somewhere:
```
https://example.com/search?q={query}
```

### What Gets Replaced
- Input: `https://example.com/search?q={query}`
- Search term: "ubuntu"
- Actual URL fetched: `https://example.com/search?q=ubuntu`

### Common Patterns
```
https://site.com/search?q={query}
https://site.com/torrents?search={query}
https://site.com/browse.php?query={query}
https://site.com/{query}
```

## What Pluggy Looks For

Pluggy scans the HTML page for:

### 1. Magnet Links (Required)
Must have `<a>` tags with `href="magnet:..."`:
```html
<a href="magnet:?xt=urn:btih:ABC123...">Ubuntu Desktop</a>
```

### 2. Title (from link text)
```html
<a href="magnet:...">Ubuntu 22.04 LTS Desktop ISO</a>
                      ↑ This becomes the title
```

### 3. Seeds/Leeches (optional, from nearby text)
Recognizes patterns like:
- "Seeds: 150"
- "Seeders: 150"
- "S:150" or "SE:150"
- "Leeches: 20"
- "Leechers: 20"
- "L:20" or "LE:20"

### 4. Size (optional, from nearby text)
Recognizes patterns like:
- "1.5 GB"
- "500 MB"
- "2.3 GiB"

## Example Page Structure

### Minimal (works)
```html
<a href="magnet:?xt=urn:btih:ABC123...">Ubuntu 22.04</a>
```

### Good (includes metadata)
```html
<div class="torrent">
  <a href="magnet:?xt=urn:btih:ABC123...">Ubuntu 22.04 Desktop</a>
  <span>Size: 3.2 GB | Seeds: 150 | Leeches: 20</span>
</div>
```

### Also Works
```html
<tr>
  <td><a href="magnet:?xt=urn:btih:ABC123...">Ubuntu 22.04</a></td>
  <td>3.2 GB</td>
  <td>150</td>
  <td>20</td>
</tr>
```

## Important Notes

### ⚠️ Legal Considerations
- Only scrape sites you own or have permission to access
- Respect robots.txt and terms of service
- Academic/legal torrent sites are ideal

### ⚠️ Technical Limitations
- **No JavaScript**: Pluggy can't run JavaScript, so dynamic sites won't work
- **HTML only**: Magnet links must be in the initial HTML
- **No authentication**: Can't log in to sites
- **Rate limiting**: Be respectful, don't spam requests

### ⚠️ Works Best With
- ✅ Static HTML pages
- ✅ Server-side rendered lists
- ✅ RSS feeds rendered as HTML
- ✅ Simple directory listings
- ✅ Sites you control

### ⚠️ Won't Work With
- ❌ JavaScript-rendered content (React, Vue, etc.)
- ❌ Sites requiring login
- ❌ Cloudflare-protected sites
- ❌ CAPTCHA-protected sites
- ❌ Sites with aggressive anti-scraping

## Troubleshooting

### No Results from HTTP Source

**Check 1: Is it enabled?**
- Settings tab → "Enable HTTP Sources" must be checked
- Search tab → "HTTP" checkbox must be checked

**Check 2: Is the URL correct?**
- Must include `{query}`
- Test the URL manually in browser first
- Example: `https://site.com/search?q=ubuntu`

**Check 3: Does the page have magnet links?**
- View page source in browser
- Look for `<a href="magnet:?xt=urn:btih:`
- Links must be in the HTML (not added by JavaScript)

**Check 4: Check console output**
If running from terminal, you'll see errors like:
```
HTTP source error for https://...: Connection timeout
HTTP source error for https://...: 404 Not Found
```

### Wrong Title/Metadata

The parser uses generic patterns. If metadata is in an unusual format:

1. Make sure info is in the same row/div as the magnet link
2. Check that format matches recognized patterns:
   - Seeds: "Seeds: 100" or "S:100"
   - Size: "1.5 GB" or "1.5GB"

### Slow Searches

HTTP sources add latency:
- Each URL = 1-3 second delay
- 5 HTTP sources = 5-15 seconds total
- This is normal - we're fetching external pages

**Tip**: Only add HTTP sources you actually use!

## Advanced: Create Your Own Torrent List

Want to host your own searchable torrent list? Here's a simple PHP example:

```php
<?php
// torrents.php
$query = $_GET['q'] ?? '';

$torrents = [
    [
        'name' => 'Ubuntu 22.04 Desktop',
        'magnet' => 'magnet:?xt=urn:btih:ABC123...',
        'size' => '3.2 GB',
        'seeds' => 150,
        'leeches' => 20
    ],
    // ... more torrents
];

// Filter by query
$results = array_filter($torrents, function($t) use ($query) {
    return stripos($t['name'], $query) !== false;
});

foreach ($results as $t): ?>
<div class="torrent">
    <a href="<?= $t['magnet'] ?>"><?= $t['name'] ?></a>
    <span>Size: <?= $t['size'] ?> | Seeds: <?= $t['seeds'] ?> | Leeches: <?= $t['leeches'] ?></span>
</div>
<?php endforeach; ?>
```

Then add to Pluggy:
```
https://yoursite.com/torrents.php?q={query}
```

## Examples of Good HTTP Sources

### Academic Torrents
Legal, public domain academic datasets:
```
https://academictorrents.com/browse.php?search={query}
```

### Internet Archive
Public domain content:
```
https://archive.org/search.php?query={query}
```

### Your Personal Media Server
For your own content:
```
https://myhomeserver.local/media/search?q={query}
```

### RSS to HTML Feed
If you have an RSS torrent feed:
```
https://feedtohtml.xyz/?feed=https://mysite.com/torrents.rss&search={query}
```

## Best Practices

1. **Start with one source** - Test it works before adding more
2. **Use reliable sites** - Sites that are always up
3. **Check legal status** - Only use legal content sources
4. **Monitor performance** - Remove slow/broken sources
5. **Keep list small** - 2-5 HTTP sources is plenty
6. **Be respectful** - Don't hammer sites with requests

## Getting Help

If HTTP sources aren't working:

1. Verify URL works in browser
2. Check page has magnet links in HTML (not JavaScript)
3. Make sure "Enable HTTP Sources" is checked
4. Check source is enabled in Search tab
5. Look at console output for error messages

## Summary

HTTP Sources let you extend Pluggy's search to any torrent listing site:
- Add URLs with `{query}` placeholder
- Pluggy fetches and parses the pages
- Magnet links become searchable results
- Works best with simple HTML pages
- Ideal for legal/academic torrent sites

Happy searching! 🔍
