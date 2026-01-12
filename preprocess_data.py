#!/usr/bin/env python3
"""
Preprocess artwork data for 3D visualization.
Parses years, maps categories, and prepares data for Three.js visualization.
"""

import json
import re
import time
from typing import Dict, List, Tuple, Optional
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

def parse_year(year_str: str) -> Tuple[float, str]:
    """
    Parse year string into numeric value and display string.
    Handles BCE, CE, ranges, and approximate dates.
    Returns (numeric_value, display_string)
    """
    if not year_str or year_str.strip() == "":
        return (0, "Unknown")
    
    year_str = year_str.strip()
    is_bce = "BCE" in year_str.upper() or "BC" in year_str.upper()
    # If no BCE/BC mentioned and year is before 1000, assume BCE for very old dates
    # Otherwise assume CE
    
    # Remove common prefixes
    year_str = re.sub(r'^c\.\s*', '', year_str, flags=re.IGNORECASE)
    year_str = re.sub(r'^ca\.\s*', '', year_str, flags=re.IGNORECASE)
    year_str = re.sub(r'^circa\s*', '', year_str, flags=re.IGNORECASE)
    
    # Handle ranges (e.g., "25,000–23,000 BCE" or "1500-1520")
    # Match numbers with optional commas (for large BCE years) or 4-digit years
    range_match = re.search(r'(\d{1,4}(?:,\d{3})*)\s*[–\-]\s*(\d{1,4}(?:,\d{3})*)', year_str)
    if range_match:
        year1 = int(range_match.group(1).replace(',', ''))
        year2 = int(range_match.group(2).replace(',', ''))
        # Use midpoint of range
        year = (year1 + year2) / 2
        display = f"{year1:,}–{year2:,} {'BCE' if is_bce else 'CE'}"
    else:
        # Extract first number found - match up to 6 digits (for very old BCE dates) or 4-digit years
        num_match = re.search(r'(\d{1,6}(?:,\d{3})*)', year_str)
        if num_match:
            year = int(num_match.group(1).replace(',', ''))
            # If no BCE/BC mentioned, assume CE (modern dates)
            if not is_bce:
                # Don't add comma for 4-digit years
                if year < 10000:
                    display = f"{year} CE"
                else:
                    display = f"{year:,} CE"
            else:
                display = f"{year:,} BCE"
        else:
            return (0, year_str)
    
    # For BCE years, we'll compress them (use negative values, will be compressed in JS)
    if is_bce:
        numeric_value = -year
    else:
        numeric_value = year
    
    return (numeric_value, display)

def geocode_location(location_str: str, geolocator: Nominatim, cache: Dict[str, Optional[Dict]]) -> Optional[Dict]:
    """
    Geocode a location string to latitude/longitude coordinates.
    Uses caching to avoid re-geocoding the same location.
    Implements progressive fallback: tries full location, then progressively more general locations.
    Returns {'lat': float, 'lng': float} or None if geocoding fails.
    """
    if not location_str or location_str.strip() == "":
        return None
    
    location_str = location_str.strip()
    
    # Check cache first
    if location_str in cache:
        return cache[location_str]
    
    # Clean up location string - extract modern location from notes
    # Handle cases like "Babylon (present-day Iraq)" -> "Iraq"
    location_clean = location_str
    if '(' in location_clean and 'present-day' in location_clean.lower():
        # Extract the modern location
        match = re.search(r'present-day\s+([^)]+)', location_clean, re.IGNORECASE)
        if match:
            location_clean = match.group(1).strip()
    # Remove parenthetical notes
    location_clean = re.sub(r'\([^)]*\)', '', location_clean).strip()
    # Remove attribution notes like "(attributed); possibly Rome"
    if ';' in location_clean:
        location_clean = location_clean.split(';')[0].strip()
    
    # Generate fallback locations to try (from most specific to most general)
    fallback_locations = [location_clean]
    
    # Remove "near" clauses and similar
    if ', near ' in location_clean.lower():
        # Try without "near X" part
        parts = re.split(r',\s*near\s+', location_clean, flags=re.IGNORECASE)
        if len(parts) > 1:
            # Keep the part after "near" and the rest
            fallback_locations.append(parts[1].strip())
            # Also try just the part before "near"
            before_near = parts[0].strip()
            if before_near:
                fallback_locations.append(before_near)
    
    # Split by commas and try progressively more general locations
    parts = [p.strip() for p in location_clean.split(',')]
    
    # Remove specific site names (common patterns)
    # Remove first part if it looks like a specific site (contains words like "cave", "shelter", "rock", etc.)
    site_keywords = ['cave', 'shelter', 'rock', 'site', 'grotte', 'grotto', 'calanque', 'karst']
    if len(parts) > 1:
        first_part_lower = parts[0].lower()
        if any(keyword in first_part_lower for keyword in site_keywords):
            # Try without the first (specific site) part
            fallback_locations.append(', '.join(parts[1:]))
    
    # Try progressively removing parts from the beginning
    for i in range(1, len(parts)):
        fallback_locations.append(', '.join(parts[i:]))
    
    # Remove duplicates while preserving order
    seen = set()
    unique_fallbacks = []
    for loc in fallback_locations:
        if loc and loc not in seen:
            seen.add(loc)
            unique_fallbacks.append(loc)
    
    # Try each fallback location
    for attempt, location_to_try in enumerate(unique_fallbacks):
        try:
            # Add delay to respect rate limits (1 second between requests)
            time.sleep(1)
            location = geolocator.geocode(location_to_try, timeout=10)
            
            if location:
                result = {'lat': location.latitude, 'lng': location.longitude}
                cache[location_str] = result
                if attempt > 0:
                    print(f"Geocoded using fallback: {location_str} -> {location_to_try}")
                return result
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            if attempt == len(unique_fallbacks) - 1:  # Last attempt
                print(f"Warning: Geocoding error for '{location_str}': {e}")
            continue
        except Exception as e:
            if attempt == len(unique_fallbacks) - 1:  # Last attempt
                print(f"Warning: Unexpected error geocoding '{location_str}': {e}")
            continue
    
    # All attempts failed
    print(f"Warning: Could not geocode: {location_str} (tried: {', '.join(unique_fallbacks[:3])}...)")
    cache[location_str] = None
    return None

def compress_bce_year(year_value: float, min_bce: float, max_ce: float) -> float:
    """
    Compress BCE years to use only 10% of axis space.
    BCE years are negative, CE years are positive.
    """
    if year_value < 0:  # BCE
        # Map BCE years to 0-0.1 range (10% of axis)
        # min_bce is the most negative (oldest) year
        bce_range = abs(min_bce)
        if bce_range == 0:
            return 0.05
        normalized = (abs(year_value) / bce_range) * 0.1
        return normalized
    else:  # CE
        # Map CE years to 0.1-1.0 range (90% of axis)
        ce_range = max_ce
        if ce_range == 0:
            return 0.5
        normalized = 0.1 + ((year_value / ce_range) * 0.9)
        return normalized

def preprocess_data(input_file: str, output_file: str, geocode: bool = True):
    """Preprocess artwork data for visualization.
    
    Args:
        input_file: Path to input JSON file
        output_file: Path to output JSON file
        geocode: If True, geocode locations to get coordinates
    """
    
    # Load data
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Flatten data structure (extract all artworks from all periods)
    artworks = []
    for period, items in data.items():
        for item in items:
            artworks.append(item)
    
    print(f"Loaded {len(artworks)} artworks")
    
    # Initialize geocoder and cache if geocoding is enabled
    geolocator = None
    geocode_cache = {}
    if geocode:
        print("Initializing geocoder...")
        geolocator = Nominatim(user_agent="artwork_visualization")
        print("Geocoding locations (this may take a while due to rate limiting)...")
    
    # Parse years and collect unique types and regions
    parsed_years = []
    types_set = set()
    regions_set = set()
    
    for artwork in artworks:
        year_value, year_display = parse_year(artwork.get('year', ''))
        parsed_years.append((year_value, year_display))
        
        art_type = artwork.get('type', 'Unknown')
        region = artwork.get('region', 'Unknown')
        
        if art_type:
            types_set.add(art_type)
        if region:
            regions_set.add(region)
    
    # Create sorted lists for mapping
    types_list = sorted(list(types_set))
    regions_list = sorted(list(regions_set))
    
    # Create mapping dictionaries
    type_to_index = {t: i for i, t in enumerate(types_list)}
    region_to_index = {r: i for i, r in enumerate(regions_list)}
    
    print(f"Found {len(types_list)} unique types: {types_list}")
    print(f"Found {len(regions_list)} unique regions: {regions_list}")
    
    # Calculate year range for compression
    year_values = [y[0] for y in parsed_years]
    min_year = min(year_values)
    max_year = max(year_values)
    min_bce = min([y for y in year_values if y < 0], default=0)
    max_ce = max([y for y in year_values if y >= 0], default=0)
    
    print(f"Year range: {min_year} to {max_year}")
    print(f"BCE range: {min_bce} to 0")
    print(f"CE range: 0 to {max_ce}")
    
    # Prepare processed artworks
    processed_artworks = []
    
    for i, artwork in enumerate(artworks):
        year_value, year_display = parsed_years[i]
        
        # Get categorical values
        art_type = artwork.get('type', 'Unknown')
        region = artwork.get('region', 'Unknown')
        
        # Map to indices (0 to n-1)
        type_index = type_to_index.get(art_type, 0)
        region_index = region_to_index.get(region, 0)
        
        # Geocode creation location if enabled
        coordinates = None
        if geocode and geolocator:
            creation_location = artwork.get('creation_location', '')
            if creation_location:
                coordinates = geocode_location(creation_location, geolocator, geocode_cache)
                if coordinates:
                    print(f"  Geocoded: {artwork.get('title', 'Unknown')} -> {coordinates}")
        
        # Create processed artwork entry
        processed = {
            'title': artwork.get('title', 'Unknown'),
            'artist': artwork.get('artist', 'Unknown'),
            'year': {
                'value': year_value,
                'display': year_display,
                'raw': artwork.get('year', '')
            },
            'type': {
                'name': art_type,
                'index': type_index
            },
            'region': {
                'name': region,
                'index': region_index
            },
            'medium': artwork.get('medium', 'Unknown'),
            'wikipedia_url': artwork.get('wikipedia_url', ''),
            'image_filename': artwork.get('image_filename', ''),
            'description': artwork.get('description', ''),
            'creation_location': artwork.get('creation_location', ''),
            'coordinates': coordinates
        }
        
        processed_artworks.append(processed)
    
    # Create output structure
    output = {
        'artworks': processed_artworks,
        'metadata': {
            'total_count': len(processed_artworks),
            'year_range': {
                'min': min_year,
                'max': max_year,
                'min_bce': min_bce,
                'max_ce': max_ce
            },
            'types': types_list,
            'regions': regions_list,
            'type_count': len(types_list),
            'region_count': len(regions_list)
        }
    }
    
    # Save processed data
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nPreprocessed data saved to {output_file}")
    print(f"Total artworks: {len(processed_artworks)}")
    print(f"Types: {len(types_list)}")
    print(f"Regions: {len(regions_list)}")
    
    return output

def generate_standalone_html(html_template_file: str, data: dict, output_html_file: str):
    """Generate standalone HTML file with embedded data."""
    # Read the HTML template
    with open(html_template_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Convert data to JSON string and escape for JavaScript
    data_json = json.dumps(data, ensure_ascii=False)
    # Escape for embedding in HTML/JavaScript
    data_json_escaped = data_json.replace('</script>', '<\\/script>')
    
    # Replace the fetch call with embedded data
    # Look for the specific pattern and replace it
    old_code = """            // Load data
            const response = await fetch('artwork_data_processed.json');
            const data = await response.json();"""
    
    new_code = f"""            // Load data - embedded directly to avoid CORS issues
            const data = {data_json_escaped};"""
    
    if old_code in html_content:
        html_content = html_content.replace(old_code, new_code)
    else:
        # Try alternative pattern
        import re
        html_content = re.sub(
            r"const response = await fetch\('artwork_data_processed\.json'\);\s*const data = await response\.json\(\);",
            f"const data = {data_json_escaped};",
            html_content
        )
    
    # Save the standalone HTML
    with open(output_html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Standalone HTML file saved to {output_html_file}")

def generate_map_standalone_html(html_template_file: str, data: dict, output_html_file: str):
    """Generate standalone HTML file for map visualization with embedded data."""
    # Read the HTML template
    with open(html_template_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Convert data to JSON string and escape for JavaScript
    data_json = json.dumps(data, ensure_ascii=False)
    # Escape for embedding in HTML/JavaScript
    data_json_escaped = data_json.replace('</script>', '<\\/script>')
    
    # Replace the fetch call with embedded data
    old_code = """            // Load data
            const response = await fetch('artwork_data_processed.json');
            const data = await response.json();"""
    
    new_code = f"""            // Load data - embedded directly to avoid CORS issues
            const data = {data_json_escaped};"""
    
    if old_code in html_content:
        html_content = html_content.replace(old_code, new_code)
    else:
        # Try alternative pattern
        import re
        html_content = re.sub(
            r"const response = await fetch\('artwork_data_processed\.json'\);\s*const data = await response\.json\(\);",
            f"const data = {data_json_escaped};",
            html_content
        )
    
    # Save the standalone HTML
    with open(output_html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Standalone map HTML file saved to {output_html_file}")

if __name__ == '__main__':
    import sys
    
    # Check if geocoding should be skipped (for faster testing)
    geocode = True
    if len(sys.argv) > 1 and sys.argv[1] == '--no-geocode':
        geocode = False
        print("Skipping geocoding (using --no-geocode flag)")
    
    data = preprocess_data('dataset_AI.json', 'artwork_data_processed.json', geocode=geocode)
    generate_standalone_html('artwork_3d_visualization.html', data, 'artwork_3d_visualization_standalone.html')
    generate_map_standalone_html('artwork_map_visualization.html', data, 'artwork_map_visualization_standalone.html')