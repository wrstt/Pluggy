"""
Search Result Model
Represents a torrent search result with deduplication support
"""
from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class SearchResult:
    """Torrent search result"""
    title: str
    magnet: str
    size: int  # bytes
    seeds: int
    leeches: int
    source: str
    infohash: str
    category: Optional[str] = None
    upload_date: Optional[str] = None
    # Aggregated links from multiple sources for the same program/version.
    link_candidates: list = field(default_factory=list)
    aggregated_sources: list = field(default_factory=list)
    link_quality: int = 0
    
    @staticmethod
    def extract_infohash(magnet: str) -> str:
        """Extract infohash from magnet link"""
        match = re.search(r'btih:([a-fA-F0-9]{40})', magnet)
        if match:
            return match.group(1).upper()
        return ""
    
    @staticmethod
    def normalize_size(size_str: str) -> int:
        """
        Normalize size string to bytes
        Handles: "1.5 GB", "500 MB", "2.3 GiB", etc.
        """
        if isinstance(size_str, int):
            return size_str
        
        size_str = size_str.strip().upper()
        
        # Extract number and unit
        match = re.match(r'([\d.]+)\s*([KMGT]I?B)', size_str)
        if not match:
            return 0
        
        value = float(match.group(1))
        unit = match.group(2)
        
        # Conversion factors (binary: KiB, MiB, GiB vs decimal: KB, MB, GB)
        multipliers = {
            'B': 1,
            'KB': 1000, 'KIB': 1024,
            'MB': 1000**2, 'MIB': 1024**2,
            'GB': 1000**3, 'GIB': 1024**3,
            'TB': 1000**4, 'TIB': 1024**4,
        }
        
        return int(value * multipliers.get(unit, 1))
    
    @staticmethod
    def format_size(bytes_size: int) -> str:
        """Format bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"
    
    def __hash__(self):
        """Hash based on infohash for deduplication"""
        return hash(self.infohash)
    
    def __eq__(self, other):
        """Equality based on infohash"""
        if isinstance(other, SearchResult):
            return self.infohash == other.infohash
        return False
    
    @property
    def size_formatted(self) -> str:
        """Get formatted size string"""
        return self.format_size(self.size)
