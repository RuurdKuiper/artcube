#!/usr/bin/env python3
"""
Wikipedia Art Dataset Enrichment Script

This script enriches the art dataset by fetching comprehensive information
from Wikipedia for each art piece and downloading the main images.
"""

import json
import os
import re
import time
import requests
from urllib.parse import quote, unquote
from typing import Dict, List, Optional

try:
    from PIL import Image
    PIL_AVAILABLE = True
    # Increase PIL's decompression bomb limit to handle very large images
    Image.MAX_IMAGE_PIXELS = None
except ImportError:
    PIL_AVAILABLE = False


class WikipediaArtEnricher:
    """Handles Wikipedia API interactions and data enrichment."""
    
    WIKIPEDIA_API_URL = "https://en.wikipedia.org/api/rest_v1"
    WIKIPEDIA_PAGE_URL = "https://en.wikipedia.org/wiki"
    
    def __init__(self, images_dir: str = "images"):
        """Initialize the enricher with an images directory."""
        self.images_dir = images_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ArtDatasetEnricher/1.0 (https://example.com/contact)'
        })
        os.makedirs(self.images_dir, exist_ok=True)
    
    def sanitize_filename(self, text: str) -> str:
        """Sanitize text for use as filename."""
        # Replace problematic characters
        text = re.sub(r'[<>:"/\\|?*]', '', text)
        text = re.sub(r'\s+', '_', text)
        text = re.sub(r'_+', '_', text)
        text = text.strip('_')
        # Limit length
        if len(text) > 200:
            text = text[:200]
        return text
    
    def search_wikipedia(self, query: str) -> Optional[str]:
        """Search Wikipedia for an article title."""
        try:
            search_url = f"{self.WIKIPEDIA_API_URL}/page/summary/{quote(query)}"
            response = self.session.get(search_url, timeout=10)
            if response.status_code == 200:
                return query
            elif response.status_code == 404:
                # Try search API
                search_api_url = "https://en.wikipedia.org/w/api.php"
                params = {
                    'action': 'query',
                    'list': 'search',
                    'srsearch': query,
                    'format': 'json',
                    'srlimit': 1
                }
                search_response = self.session.get(search_api_url, params=params, timeout=10)
                if search_response.status_code == 200:
                    data = search_response.json()
                    if 'query' in data and 'search' in data['query'] and len(data['query']['search']) > 0:
                        return data['query']['search'][0]['title']
            return None
        except Exception as e:
            print(f"  Error searching Wikipedia: {e}")
            return None
    
    def get_page_summary(self, title: str) -> Optional[Dict]:
        """Get page summary/extract from Wikipedia."""
        try:
            url = f"{self.WIKIPEDIA_API_URL}/page/summary/{quote(title)}"
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"  Error getting summary: {e}")
            return None
    
    def get_page_content(self, title: str) -> Optional[Dict]:
        """Get full page content with infobox data."""
        try:
            url = f"{self.WIKIPEDIA_API_URL}/page/html/{quote(title)}"
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                # Also get structured data
                structured_url = f"{self.WIKIPEDIA_API_URL}/page/structured-content/{quote(title)}"
                structured_response = self.session.get(structured_url, timeout=10)
                structured_data = None
                if structured_response.status_code == 200:
                    structured_data = structured_response.json()
                
                return {
                    'html': response.text,
                    'structured': structured_data
                }
            return None
        except Exception as e:
            print(f"  Error getting content: {e}")
            return None
    
    def extract_infobox_data(self, title: str) -> Dict:
        """Extract data from Wikipedia infobox using API."""
        infobox_data = {}
        
        try:
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'prop': 'revisions|pageimages',
                'titles': title,
                'rvprop': 'content',
                'rvslots': 'main',
                'piprop': 'original',
                'pithumbsize': 2000,
                'format': 'json'
            }
            response = self.session.get(api_url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})
                if pages:
                    page_data = list(pages.values())[0]
                    
                    # Extract image
                    if 'original' in page_data:
                        original = page_data['original']
                        if isinstance(original, dict) and 'source' in original:
                            infobox_data['image_url'] = original['source']
                    
                    # Parse infobox from revision content
                    if 'revisions' in page_data and len(page_data['revisions']) > 0:
                        content = page_data['revisions'][0]['slots']['main']['*']
                        infobox_data.update(self._parse_infobox(content))
        except Exception as e:
            print(f"  Error extracting infobox: {e}")
        
        return infobox_data
    
    def _parse_infobox(self, content: str) -> Dict:
        """Parse infobox data from Wikipedia markup."""
        data = {}
        
        # Extract common infobox fields (try multiple patterns for same field)
        location_patterns = [
            r'\|\s*location\s*=\s*([^\n|]+)',
            r'\|\s*museum\s*=\s*([^\n|]+)',
            r'\|\s*collection\s*=\s*([^\n|]+)',
            r'\|\s*repository\s*=\s*([^\n|]+)'
        ]
        dimensions_patterns = [
            r'\|\s*dimensions\s*=\s*([^\n|]+)',
            r'\|\s*size\s*=\s*([^\n|]+)',
            r'\|\s*height\s*=\s*([^\n|]+)'
        ]
        
        # Try location patterns
        for pattern in location_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match and 'location' not in data:
                value = match.group(1).strip()
                value = re.sub(r'\[\[([^\]]+)\]\]', r'\1', value)  # Remove wikilinks
                value = re.sub(r'\{\{.*?\}\}', '', value)  # Remove templates
                data['location'] = value
                break
        
        # Try dimensions patterns
        for pattern in dimensions_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match and 'dimensions' not in data:
                value = match.group(1).strip()
                value = re.sub(r'\[\[([^\]]+)\]\]', r'\1', value)
                value = re.sub(r'\{\{.*?\}\}', '', value)
                data['dimensions'] = value
                break
        
        # Single patterns
        single_patterns = {
            'medium': r'\|\s*medium\s*=\s*([^\n|]+)',
            'style': r'\|\s*style\s*=\s*([^\n|]+)',
            'movement': r'\|\s*movement\s*=\s*([^\n|]+)',
        }
        
        for key, pattern in single_patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match and key not in data:
                value = match.group(1).strip()
                value = re.sub(r'\[\[([^\]]+)\]\]', r'\1', value)
                value = re.sub(r'\{\{.*?\}\}', '', value)
                data[key] = value
        
        return data
    
    def _is_svg_url(self, url: str) -> bool:
        """Check if a URL points to an SVG file (which we want to skip)."""
        if not url:
            return False
        url_lower = url.lower()
        # Check for .svg extension (may be URL-encoded or in query params)
        return '.svg' in url_lower or '%2Esvg' in url_lower or '%2esvg' in url_lower
    
    def get_image_url(self, title: str) -> Optional[str]:
        """Get the main image URL for a Wikipedia article using multiple methods.
        Skips SVG files as they are usually logos/icons, not artwork photos."""
        try:
            api_url = "https://en.wikipedia.org/w/api.php"
            
            # Method 1: Try to get original image URL via pageimages API
            params = {
                'action': 'query',
                'prop': 'pageimages',
                'titles': title,
                'piprop': 'original|thumbnail',
                'pithumbsize': 2000,
                'format': 'json'
            }
            response = self.session.get(api_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})
                if pages:
                    page_data = list(pages.values())[0]
                    
                    # Try original first
                    if 'original' in page_data:
                        original = page_data['original']
                        if isinstance(original, dict) and 'source' in original:
                            url = original['source']
                            if not self._is_svg_url(url):
                                return url
                        elif isinstance(original, str):
                            if not self._is_svg_url(original):
                                return original
            
                    # Try thumbnail and convert to original
                    if 'thumbnail' in page_data:
                        thumbnail = page_data['thumbnail']
                        if isinstance(thumbnail, dict) and 'source' in thumbnail:
                            thumbnail_url = thumbnail['source']
                            # Convert thumbnail URL to original
                            original_url = self._thumbnail_to_original(thumbnail_url)
                            if original_url and not self._is_svg_url(original_url):
                                return original_url
            
            # Method 2: Try from page summary thumbnail
            summary = self.get_page_summary(title)
            if summary and 'thumbnail' in summary:
                thumbnail_url = summary['thumbnail']['source']
                original_url = self._thumbnail_to_original(thumbnail_url)
                if original_url and not self._is_svg_url(original_url):
                    return original_url
            
            # Method 3: Try parsing HTML for infobox image
            try:
                page_url = f"{self.WIKIPEDIA_PAGE_URL}/{quote(title)}"
                html_response = self.session.get(page_url, timeout=10)
                if html_response.status_code == 200:
                    html_content = html_response.text
                    
                    # Look for infobox image
                    # Pattern: <img src="..." in infobox
                    infobox_pattern = r'<table[^>]*class="[^"]*infobox[^"]*"[^>]*>.*?<img[^>]*(?:src|data-src)="([^"]+)"'
                    match = re.search(infobox_pattern, html_content, re.DOTALL | re.IGNORECASE)
                    if match:
                        img_src = match.group(1)
                        # Convert to full URL if relative
                        if img_src.startswith('//'):
                            img_src = 'https:' + img_src
                        elif img_src.startswith('/'):
                            img_src = 'https://en.wikipedia.org' + img_src
                        # Convert thumbnail to original
                        original_url = self._thumbnail_to_original(img_src)
                        if original_url and not self._is_svg_url(original_url):
                            return original_url
                    
                    # Also look for images in the main content area (not just infobox)
                    # Many artwork pages have the main image in the content, not infobox
                    content_img_pattern = r'<div[^>]*class="[^"]*mw-parser-output[^"]*"[^>]*>.*?<img[^>]*(?:src|data-src)="([^"]+)"'
                    content_match = re.search(content_img_pattern, html_content, re.DOTALL | re.IGNORECASE)
                    if content_match:
                        img_src = content_match.group(1)
                        if img_src.startswith('//'):
                            img_src = 'https:' + img_src
                        elif img_src.startswith('/'):
                            img_src = 'https://en.wikipedia.org' + img_src
                        # Check if it's a Wikimedia URL
                        if 'upload.wikimedia.org' in img_src:
                            original_url = self._thumbnail_to_original(img_src)
                            if original_url and not self._is_svg_url(original_url):
                                return original_url
                    
                    # Method 4: Look for direct upload.wikimedia.org links in the page
                    # This catches images that are already original URLs
                    # Pattern needs to handle:
                    # - URL-encoded characters (%27, %2C, etc.)
                    # - URLs in various attributes (src, href, data-src, etc.)
                    # - URLs that might span multiple lines
                    # - Both commons and en namespaces
                    
                    # More comprehensive pattern that handles various contexts
                    # Look for upload.wikimedia.org URLs in any attribute or as standalone URLs
                    # The pattern: upload.wikimedia.org/wikipedia/(commons|en)/[hash]/[hash]/[filename]
                    # Where [hash] is a single hex character, and filename can contain URL-encoded chars
                    
                    # Pattern 1: In HTML attributes (src, href, data-*, etc.)
                    # Exclude SVG files as they are usually logos/icons, not artwork photos
                    attr_pattern = r'(?:src|href|data-src|data-image|data-file|data-original)="(https://upload\.wikimedia\.org/wikipedia/(?:commons|en)/[a-f0-9]/[a-f0-9]{2}/[^"]+\.(?:jpg|jpeg|png|gif|webp))"'
                    
                    # Pattern 2: Standalone URLs (in JSON, JavaScript, or plain text)
                    # This pattern is more flexible and handles URL encoding
                    # Exclude SVG files as they are usually logos/icons, not artwork photos
                    standalone_pattern = r'https://upload\.wikimedia\.org/wikipedia/(?:commons|en)/[a-f0-9]/[a-f0-9]{2}/[^\s"\'<>\)]+(?:%[0-9a-fA-F]{2})*[^\s"\'<>\)]*\.(?:jpg|jpeg|png|gif|webp)'
                    
                    all_matches = []
                    
                    # Search in attributes
                    attr_matches = re.findall(attr_pattern, html_content, re.IGNORECASE | re.MULTILINE)
                    if attr_matches:
                        all_matches.extend(attr_matches)
                    
                    # Search for standalone URLs
                    standalone_matches = re.findall(standalone_pattern, html_content, re.IGNORECASE | re.MULTILINE)
                    if standalone_matches:
                        all_matches.extend(standalone_matches)
                    
                    # Remove duplicates and decode URLs
                    unique_matches = []
                    seen = set()
                    for url in all_matches:
                        # Decode URL-encoded characters
                        try:
                            decoded_url = unquote(url) if '%' in url else url
                        except:
                            decoded_url = url
                        
                        # Normalize the URL (remove trailing query params, fragments, etc.)
                        normalized = decoded_url.split('?')[0].split('#')[0]
                        
                        if normalized not in seen:
                            seen.add(normalized)
                            unique_matches.append(normalized)
                    
                    if unique_matches:
                        # Prefer original URLs (not thumbnails) and commons over en
                        # Also prefer images that seem to be the main artwork image
                        # Skip SVG files
                        for url in unique_matches:
                            if '/thumb/' not in url and not self._is_svg_url(url):
                                # Prefer commons namespace
                                if '/commons/' in url:
                                    return url
                        
                        # If no commons found, return first non-thumbnail (non-SVG)
                        for url in unique_matches:
                            if '/thumb/' not in url and not self._is_svg_url(url):
                                return url
                        
                        # If only thumbnails found, convert the first non-SVG one
                        for url in unique_matches:
                            original_url = self._thumbnail_to_original(url)
                            if original_url and not self._is_svg_url(original_url):
                                return original_url
                    
                    # Method 5: Look for data-src or data-image attributes (lazy-loaded images)
                    # Exclude SVG files as they are usually logos/icons, not artwork photos
                    lazy_pattern = r'(?:data-src|data-image)="([^"]*upload\.wikimedia\.org[^"]+\.(?:jpg|jpeg|png|gif|webp))"'
                    lazy_matches = re.findall(lazy_pattern, html_content, re.IGNORECASE)
                    if lazy_matches:
                        for url in lazy_matches:
                            if not url.startswith('http'):
                                url = 'https:' + url if url.startswith('//') else 'https://en.wikipedia.org' + url
                            # Skip SVG files
                            if self._is_svg_url(url):
                                continue
                            if '/thumb/' not in url:
                                return url
                            original_url = self._thumbnail_to_original(url)
                            if original_url and not self._is_svg_url(original_url):
                                return original_url
            except Exception as e:
                pass  # Silently fail HTML parsing
            
            return None
        except Exception as e:
            print(f"  Error getting image URL: {e}")
            return None
    
    def _thumbnail_to_original(self, thumbnail_url: str) -> Optional[str]:
        """Convert a Wikipedia thumbnail URL to the original image URL."""
        if not thumbnail_url:
            return None
        
        # Handle different thumbnail URL formats
        # Format 1: /thumb/path/to/image.jpg/300px-image.jpg
        if '/thumb/' in thumbnail_url:
            # Extract the original path
            parts = thumbnail_url.split('/thumb/')
            if len(parts) == 2:
                original_path = parts[1].rsplit('/', 1)[0]  # Remove the thumbnail filename
                # Determine base URL and namespace
                if 'upload.wikimedia.org' in thumbnail_url:
                    # Check which namespace (commons or en)
                    if '/commons/thumb/' in thumbnail_url:
                        return f"https://upload.wikimedia.org/wikipedia/commons/{original_path}"
                    elif '/en/thumb/' in thumbnail_url:
                        return f"https://upload.wikimedia.org/wikipedia/en/{original_path}"
                    else:
                        # Default to commons if namespace not clear
                        return f"https://upload.wikimedia.org/wikipedia/commons/{original_path}"
                elif 'wikipedia.org' in thumbnail_url:
                    # Extract namespace from URL
                    if '/commons/thumb/' in thumbnail_url:
                        return f"https://upload.wikimedia.org/wikipedia/commons/{original_path}"
                    elif '/en/thumb/' in thumbnail_url:
                        return f"https://upload.wikimedia.org/wikipedia/en/{original_path}"
        
        # Format 2: Already an original URL (no /thumb/ in path)
        if 'upload.wikimedia.org' in thumbnail_url and '/thumb/' not in thumbnail_url:
            return thumbnail_url
        
        # Format 3: Try to construct from thumbnail
        # If it's a thumbnail, try to get the original
        if 'thumb' in thumbnail_url.lower() and 'px-' in thumbnail_url:
            # Remove the thumbnail size part
            original = re.sub(r'/\d+px-[^/]+$', '', thumbnail_url)
            original = original.replace('/thumb/', '/')
            # Preserve namespace (commons or en) in the path
            if '/commons/' in thumbnail_url and '/commons/' not in original:
                original = original.replace('/wikipedia/', '/wikipedia/commons/')
            elif '/en/' in thumbnail_url and '/en/' not in original and '/commons/' not in original:
                original = original.replace('/wikipedia/', '/wikipedia/en/')
            return original
        
            return None
    
    def download_image(self, image_url: str, filename: str, max_size_mb: float = 1.0) -> bool:
        """Download an image from URL to filename and resize to be under max_size_mb."""
        try:
            response = self.session.get(image_url, timeout=15, stream=True)
            if response.status_code == 200:
                filepath = os.path.join(self.images_dir, filename)
                
                # Download to temporary file first
                temp_path = filepath + '.tmp'
                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Resize image if it's too large and PIL is available
                if PIL_AVAILABLE:
                    try:
                        self._resize_image_if_needed(temp_path, filepath, max_size_mb)
                    except Exception as e:
                        print(f"  Warning: Could not resize image: {e}")
                        # If resizing fails, just use the original
                        os.rename(temp_path, filepath)
                else:
                    # If PIL not available, just use the downloaded file
                    os.rename(temp_path, filepath)
                
                return True
            return False
        except Exception as e:
            print(f"  Error downloading image: {e}")
            # Clean up temp file if it exists
            temp_path = os.path.join(self.images_dir, filename + '.tmp')
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
    
    def _resize_image_if_needed(self, input_path: str, output_path: str, max_size_mb: float = 1.0) -> None:
        """Resize image to be under max_size_mb MB if needed."""
        def get_file_size_mb(path: str) -> float:
            return os.path.getsize(path) / (1024 * 1024)
        
        current_size_mb = get_file_size_mb(input_path)
        
        if current_size_mb <= max_size_mb:
            # Image is already small enough, just rename
            os.rename(input_path, output_path)
            return
        
        # Need to resize
        max_dimension = 2000
        
        with Image.open(input_path) as img:
            # Convert to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            width, height = img.size
            quality = 85
            
            # If file is extremely large, aggressively reduce dimensions first
            if current_size_mb > 10:
                aggressive_max_dim = 1200
                if max(width, height) > aggressive_max_dim:
                    if width > height:
                        new_width = aggressive_max_dim
                        new_height = int(height * (aggressive_max_dim / width))
                    else:
                        new_height = aggressive_max_dim
                        new_width = int(width * (aggressive_max_dim / height))
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            elif max(width, height) > max_dimension:
                if width > height:
                    new_width = max_dimension
                    new_height = int(height * (max_dimension / width))
                else:
                    new_height = max_dimension
                    new_width = int(width * (max_dimension / height))
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Save with decreasing quality until we're under the size limit
            attempts = 0
            max_attempts = 20
            
            while attempts < max_attempts:
                img.save(output_path, format='JPEG', quality=quality, optimize=True)
                new_size_mb = get_file_size_mb(output_path)
                
                if new_size_mb <= max_size_mb:
                    break
                
                # If still too large, reduce dimensions further
                if attempts > 5 and new_size_mb > max_size_mb * 1.5:
                    width, height = img.size
                    img = img.resize((int(width * 0.9), int(height * 0.9)), Image.Resampling.LANCZOS)
                
                quality = max(50, quality - 5)
                attempts += 1
            
            # Remove temp file
            if os.path.exists(input_path):
                os.remove(input_path)
    
    def enrich_art_piece(self, art_piece: Dict) -> Dict:
        """Enrich a single art piece with Wikipedia data."""
        title = art_piece['title']
        artist = art_piece.get('artist', 'Unknown')
        
        print(f"\nProcessing: {title} by {artist}")
        
        enriched = art_piece.copy()
        
        # Initialize default values
        enriched['wikipedia_url'] = None
        enriched['description'] = None
        enriched['location'] = None
        enriched['medium'] = None
        enriched['dimensions'] = None
        enriched['style'] = None
        enriched['significance'] = None
        enriched['image_filename'] = None
        
        # FIRST: Check if we already have an image for this artwork
        # If image exists, skip Wikipedia entirely
        sanitized_artist = self.sanitize_filename(artist)
        sanitized_title = self.sanitize_filename(title)
        base_filename = f"{sanitized_artist}_{sanitized_title}"
        
        # Check for existing images with various extensions
        existing_image = None
        # Check for existing images (excluding SVG)
        for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            potential_filename = f"{base_filename}{ext}"
            potential_path = os.path.join(self.images_dir, potential_filename)
            if os.path.exists(potential_path):
                existing_image = potential_filename
                print(f"  ✓ Image already exists: {existing_image}")
                enriched['image_filename'] = f"images/{existing_image}"
                # Skip Wikipedia if image already exists
                return enriched
        
        # Only if image doesn't exist, search Wikipedia
        # Search for Wikipedia article
        wiki_title = self.search_wikipedia(title)
        if not wiki_title:
            print(f"  ⚠️  Wikipedia article not found for '{title}'")
            return enriched
        
        print(f"  Found Wikipedia article: {wiki_title}")
        
        # Get page summary
        summary = self.get_page_summary(wiki_title)
        if summary:
            enriched['wikipedia_url'] = f"{self.WIKIPEDIA_PAGE_URL}/{quote(wiki_title)}"
            enriched['description'] = summary.get('extract', '')
            
            # Extract additional information from infobox
            infobox_data = self.extract_infobox_data(wiki_title)
            
            enriched['location'] = infobox_data.get('location', None)
            enriched['medium'] = infobox_data.get('medium', None)
            enriched['dimensions'] = infobox_data.get('dimensions', None)
            enriched['style'] = infobox_data.get('style', None) or infobox_data.get('movement', None)
            
            # Extract significance from description if available
            if enriched['description']:
                # Could add logic here to extract key points about significance
                pass
        
        # Get and download image from Wikipedia
        image_url = self.get_image_url(wiki_title)
        if image_url:
            print(f"  Found image: {image_url[:80]}...")
            
            # Always save as .jpg since we resize and convert to JPEG
            # This ensures consistent format and size
            image_filename = f"{base_filename}.jpg"
            image_path = os.path.join(self.images_dir, image_filename)
            
            # Double-check if image exists (check for .jpg or other extensions)
            if os.path.exists(image_path):
                print(f"  Image already exists: {image_filename}")
                enriched['image_filename'] = f"images/{image_filename}"
            else:
                # Also check for other extensions
                found_existing = False
                # Check for existing images (excluding SVG)
                for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                    potential_path = os.path.join(self.images_dir, f"{base_filename}{ext}")
                    if os.path.exists(potential_path):
                        print(f"  Image already exists: {base_filename}{ext}")
                        enriched['image_filename'] = f"images/{base_filename}{ext}"
                        found_existing = True
                        break
                
                if not found_existing:
                    if self.download_image(image_url, image_filename):
                        print(f"  ✓ Downloaded and resized image: {image_filename}")
                        enriched['image_filename'] = f"images/{image_filename}"
                    else:
                        print(f"  ⚠️  Failed to download image")
                        enriched['image_filename'] = None
        else:
            print(f"  ⚠️  No image found")
            enriched['image_filename'] = None
        
        # Small delay to be respectful to Wikipedia API
        time.sleep(0.5)
        
        return enriched


def main():
    """Main function to enrich the dataset."""
    print("Wikipedia Art Dataset Enrichment")
    print("=" * 50)
    
    # Read input dataset
    input_file = "dataset.json"
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found!")
        return
    
    with open(input_file, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    print(f"Loaded {sum(len(pieces) for pieces in dataset.values())} art pieces from {input_file}")
    
    # Initialize enricher
    enricher = WikipediaArtEnricher()
    
    # Enrich dataset
    enriched_dataset = {}
    total_pieces = sum(len(pieces) for pieces in dataset.values())
    current_piece = 0
    
    for period, art_pieces in dataset.items():
        print(f"\n{'=' * 50}")
        print(f"Processing period: {period}")
        print(f"{'=' * 50}")
        
        enriched_pieces = []
        for art_piece in art_pieces:
            current_piece += 1
            print(f"\n[{current_piece}/{total_pieces}]")
            enriched_piece = enricher.enrich_art_piece(art_piece)
            enriched_pieces.append(enriched_piece)
        
        enriched_dataset[period] = enriched_pieces
    
    # Write output
    output_file = "dataset_complete.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(enriched_dataset, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 50}")
    print(f"✓ Enrichment complete!")
    print(f"✓ Saved to {output_file}")
    print(f"✓ Images saved to {enricher.images_dir}/")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
