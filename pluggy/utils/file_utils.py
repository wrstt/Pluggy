"""
File Utilities
Cross-platform file operations with safe filename handling
"""
import re
from pathlib import Path
from typing import Union


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Create a safe filename for cross-platform use
    
    Removes/replaces characters that are problematic on Windows, macOS, or Linux
    
    Args:
        filename: Original filename
        max_length: Maximum filename length (default 255)
    
    Returns:
        Sanitized filename
    """
    # Remove/replace invalid characters
    # Windows: < > : " / \ | ? *
    # Also handle control characters
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    safe = re.sub(invalid_chars, '_', filename)
    
    # Remove leading/trailing periods and spaces (Windows issues)
    safe = safe.strip('. ')
    
    # Handle reserved names on Windows
    reserved = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    name_parts = safe.rsplit('.', 1)
    base_name = name_parts[0].upper()
    
    if base_name in reserved:
        safe = f"_{safe}"
    
    # Truncate if too long (preserve extension if possible)
    if len(safe) > max_length:
        if len(name_parts) > 1:
            ext = name_parts[1]
            safe = name_parts[0][:max_length - len(ext) - 1] + '.' + ext
        else:
            safe = safe[:max_length]
    
    return safe or 'unnamed'


def ensure_path_exists(path: Union[str, Path]) -> Path:
    """
    Ensure a directory path exists, creating it if necessary
    
    Args:
        path: Directory path
    
    Returns:
        Path object
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_unique_filename(directory: Path, filename: str) -> Path:
    """
    Get a unique filename in a directory by appending numbers if needed
    
    Args:
        directory: Target directory
        filename: Desired filename
    
    Returns:
        Unique Path in the directory
    """
    path = directory / filename
    
    if not path.exists():
        return path
    
    # Split filename and extension
    name = path.stem
    ext = path.suffix
    
    counter = 1
    while True:
        new_name = f"{name} ({counter}){ext}"
        new_path = directory / new_name
        if not new_path.exists():
            return new_path
        counter += 1


def format_size_bytes(size_bytes: int) -> str:
    """
    Format byte size to human-readable string
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"
