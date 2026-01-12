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
    
    def get_image_url(self, title: str) -> Optional[str]:
        """Get the main image URL for a Wikipedia article."""
        try:
            # Try to get original image URL via API
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'prop': 'pageimages',
                'titles': title,
                'piprop': 'original',
                'pithumbsize': 2000,
                'format': 'json'
            }
            response = self.session.get(api_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})
                if pages:
                    page_data = list(pages.values())[0]
                    if 'original' in page_data:
                        original = page_data['original']
                        if isinstance(original, dict) and 'source' in original:
                            return original['source']
                        elif isinstance(original, str):
                            return original
            
            # Alternative: try from page summary thumbnail
            summary = self.get_page_summary(title)
            if summary and 'thumbnail' in summary:
                # Extract thumbnail URL and try to get full size
                thumbnail_url = summary['thumbnail']['source']
                # Try to get larger version
                if 'thumb' in thumbnail_url:
                    # Replace thumbnail path to get original
                    original_url = thumbnail_url.split('/thumb/')[1].rsplit('/', 1)[0] if '/thumb/' in thumbnail_url else None
                    if original_url:
                        return f"https://upload.wikimedia.org/wikipedia/commons/{original_url}"
            
            return None
        except Exception as e:
            print(f"  Error getting image URL: {e}")
            return None
    
    def download_image(self, image_url: str, filename: str) -> bool:
        """Download an image from URL to filename."""
        try:
            response = self.session.get(image_url, timeout=15, stream=True)
            if response.status_code == 200:
                filepath = os.path.join(self.images_dir, filename)
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            return False
        except Exception as e:
            print(f"  Error downloading image: {e}")
            return False
    
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
        
        # Get and download image
        image_url = self.get_image_url(wiki_title)
        if image_url:
            print(f"  Found image: {image_url[:80]}...")
            # Create sanitized filename
            sanitized_artist = self.sanitize_filename(artist)
            sanitized_title = self.sanitize_filename(title)
            base_filename = f"{sanitized_artist}_{sanitized_title}"
            
            # Determine file extension from URL
            extension = '.jpg'  # default
            if '.png' in image_url.lower():
                extension = '.png'
            elif '.svg' in image_url.lower():
                extension = '.svg'
            elif '.webp' in image_url.lower():
                extension = '.webp'
            elif '.gif' in image_url.lower():
                extension = '.gif'
            
            image_filename = f"{base_filename}{extension}"
            image_path = os.path.join(self.images_dir, image_filename)
            
            # Check if image is already downloaded
            if os.path.exists(image_path):
                print(f"  Image already exists: {image_filename}")
            else:
                if self.download_image(image_url, image_filename):
                    print(f"  ✓ Downloaded image: {image_filename}")
                else:
                    print(f"  ⚠️  Failed to download image")
                    image_filename = None
            
            enriched['image_filename'] = f"images/{image_filename}" if image_filename else None
        else:
            print(f"  ⚠️  No image found")
        
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
