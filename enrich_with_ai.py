#!/usr/bin/env python3
"""
AI Art Dataset Enrichment Script

This script uses OpenAI's ChatGPT API to enrich art pieces with missing information,
including adding 'type' and 'region' categories.
"""

import json
import os
import sys
import time
from typing import Dict, List, Optional
import openai
from dotenv import load_dotenv


# Define available types
ART_TYPES = [
    "painting",
    "sculpture",
    "architecture",
    "drawing",
    "print",
    "photography",
    "installation",
    "textile",
    "ceramic",
    "mosaic",
    "other"
]

# Define available regions
REGIONS = {
    "Europe & Mediterranean": {
        "Western Europe": ["Italy", "France", "Spain", "Low Countries", "UK", "Germany", "Switzerland"],
        "Eastern Europe & Russia": ["Balkans", "Baltics", "Ukraine", "Russia (European side)"],
        "Ancient Near East": ["Mesopotamia", "Levant", "Anatolia", "Persia"],
        "Ancient Egypt & Nubia": ["Nile Valley cultures only"]
    },
    "Africa & Islamic world": {
        "Islamic World": ["Islamic art across regions (post-7th century; cultural, not geographic)"],
        "Sub-Saharan Africa": ["Africa south of the Sahara (non-Islamic classification)"]
    },
    "Asia & Oceania": {
        "South Asia": ["Indian subcontinent"],
        "Central Asia": ["Silk Road & steppe cultures"],
        "East Asia": ["China", "Korea", "Japan"],
        "Southeast Asia": ["Thailand", "Cambodia", "Vietnam", "Indonesia", "Philippines"],
        "Australasia & Oceania": ["Australia", "New Zealand", "Pacific Islands"]
    },
    "Americas": {
        "North America": ["Present-day USA & Canada (both Indigenous + later art)"],
        "Mesoamerica": ["Mexico & Central America (Olmec, Maya, Aztec, Mixtec, etc.)"],
        "South America (Andean & Amazonian)": ["Andes & surrounding regions (Inca, Moche, Nazca, etc.)"]
    }
}


def format_regions_for_prompt() -> str:
    """Format regions for inclusion in the prompt."""
    lines = []
    for major_region, sub_regions in REGIONS.items():
        lines.append(f"{major_region}:")
        for sub_region, examples in sub_regions.items():
            lines.append(f"  - {sub_region}")
            if examples:
                lines.append(f"    Examples: {', '.join(examples)}")
    return "\n".join(lines)


def create_prompt(art_piece: Dict) -> str:
    """Create a prompt for ChatGPT to enrich an art piece."""
    
    # Example of a filled-in artwork
    example = {
        "title": "Mona Lisa",
        "artist": "Leonardo da Vinci",
        "year": "c. 1503",
        "wikipedia_url": "https://en.wikipedia.org/wiki/Mona_Lisa",
        "description": "The Mona Lisa is a half-length portrait painting by Italian artist Leonardo da Vinci...",
        "current_location": "Louvre Museum, Paris, France",
        "creation_location": "Florence, Italy",
        "medium": "Oil on poplar wood panel",
        "dimensions": "77 cm × 53 cm (30 in × 21 in)",
        "style": "High Renaissance",
        "significance": "One of the most famous paintings in the world, known for its enigmatic smile and masterful technique.",
        "image_filename": "images/Leonardo_da_Vinci_Mona_Lisa.jpg",
        "type": "painting",
        "region": "Western Europe"
    }
    
    prompt = f"""You are an art historian expert. Your task is to enrich the following art piece with complete information.

CURRENT DATA (you can edit any field if you have better information):
{json.dumps(art_piece, indent=2)}

AVAILABLE ART TYPES (choose exactly one):
{', '.join(ART_TYPES)}

AVAILABLE REGIONS (choose exactly one main category):
{format_regions_for_prompt()}

For the region field, return ONLY the main category name (e.g., "Western Europe", "East Asia", "North America", etc.), not the subcategory.

EXAMPLE OF COMPLETE ARTWORK:
{json.dumps(example, indent=2)}

INSTRUCTIONS:
1. Fill in ALL missing or null fields with accurate information
2. Correct any incorrect information in the current data if you know better
3. Choose the appropriate "type" from the available options (or "other" if none fit)
4. Choose the appropriate "region" from the available main categories
5. Provide "current_location": where the artwork is currently housed (museum, collection, etc.). Use null if unknown or if the artwork no longer exists.
6. Provide "creation_location": where the artwork was originally created (city, region, etc.). Use null if unknown.
7. If the current data has a "location" field, interpret it as "current_location" unless you know it refers to creation location.
8. Ensure "medium" describes the material/technique (e.g., "Oil on canvas", "Marble", "Fresco")
9. Ensure "dimensions" includes size information if available
10. Ensure "style" describes the art movement or style period
11. Ensure "significance" provides a brief explanation of why this artwork is important
12. Keep the "image_filename" field as is
13. Return ONLY valid JSON, no additional text or markdown formatting

Return the complete JSON object for this artwork:"""
    
    return prompt


def enrich_art_piece_with_ai(client: openai.OpenAI, art_piece: Dict, model: str = "gpt-4.1") -> Dict:
    """Enrich a single art piece using OpenAI API."""
    prompt = create_prompt(art_piece)
    content = ""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert art historian. Return only valid JSON, no additional text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        enriched = json.loads(content)
        
        # Validate required fields
        required_fields = ["title", "artist", "year", "type", "region"]
        for field in required_fields:
            if field not in enriched:
                print(f"  ⚠️  Warning: Missing field '{field}' in response")
        
        # Validate type
        if enriched.get("type") not in ART_TYPES:
            print(f"  ⚠️  Warning: Invalid type '{enriched.get('type')}', should be one of {ART_TYPES}")
        
        # Validate region (check if it's a main category)
        valid_regions = []
        for major_region, sub_regions in REGIONS.items():
            valid_regions.extend(sub_regions.keys())
        
        if enriched.get("region") not in valid_regions:
            print(f"  ⚠️  Warning: Region '{enriched.get('region')}' may not be a valid main category")
        
        return enriched
        
    except json.JSONDecodeError as e:
        print(f"  ❌ Error parsing JSON response: {e}")
        if content:
            print(f"  Response was: {content[:200]}...")
        return art_piece  # Return original if parsing fails
    except Exception as e:
        print(f"  ❌ Error calling OpenAI API: {e}")
        return art_piece  # Return original on error


def save_dataset(output_file: str, enriched_dataset: Dict) -> None:
    """Save the enriched dataset to JSON file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(enriched_dataset, f, indent=2, ensure_ascii=False)


def print_artwork_result(enriched_piece: Dict) -> None:
    """Print the enriched artwork result in a readable format."""
    print("\n" + "─" * 50)
    print("ENRICHED RESULT:")
    print("─" * 50)
    print(f"Title: {enriched_piece.get('title', 'N/A')}")
    print(f"Artist: {enriched_piece.get('artist', 'N/A')}")
    print(f"Year: {enriched_piece.get('year', 'N/A')}")
    print(f"Type: {enriched_piece.get('type', 'N/A')}")
    print(f"Region: {enriched_piece.get('region', 'N/A')}")
    print(f"Current Location: {enriched_piece.get('current_location', 'N/A')}")
    print(f"Creation Location: {enriched_piece.get('creation_location', 'N/A')}")
    print(f"Medium: {enriched_piece.get('medium', 'N/A')}")
    print(f"Dimensions: {enriched_piece.get('dimensions', 'N/A')}")
    print(f"Style: {enriched_piece.get('style', 'N/A')}")
    if enriched_piece.get('significance'):
        significance = enriched_piece.get('significance', '')
        if len(significance) > 100:
            print(f"Significance: {significance[:100]}...")
        else:
            print(f"Significance: {significance}")
    print("─" * 50)


def main(print_results: bool = True):
    """Main function to enrich the dataset with AI.
    
    Args:
        print_results: If True, print the enriched result after each artwork.
    """
    print("AI Art Dataset Enrichment")
    print("=" * 50)
    
    # Check for API key
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set!")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
        return
    
    # Initialize OpenAI client
    client = openai.OpenAI(api_key=api_key)
    
    # Read input dataset
    input_file = "dataset_complete.json"
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found!")
        return
    
    with open(input_file, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    total_pieces = sum(len(pieces) for pieces in dataset.values())
    print(f"Loaded {total_pieces} art pieces from {input_file}")
    
    # Check if output file exists and load it to resume
    output_file = "dataset_AI.json"
    enriched_dataset = {}
    if os.path.exists(output_file):
        print(f"\nFound existing {output_file}, loading to resume...")
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                enriched_dataset = json.load(f)
            print(f"Resumed with {sum(len(pieces) for pieces in enriched_dataset.values())} already processed artworks")
        except Exception as e:
            print(f"Warning: Could not load existing file: {e}")
            print("Starting fresh...")
    
    # Enrich dataset
    current_piece = 0
    
    for period, art_pieces in dataset.items():
        print(f"\n{'=' * 50}")
        print(f"Processing period: {period}")
        print(f"{'=' * 50}")
        
        # Initialize period if not exists
        if period not in enriched_dataset:
            enriched_dataset[period] = []
        
        # Process each art piece
        for idx, art_piece in enumerate(art_pieces):
            # Skip if already processed (resume capability)
            if idx < len(enriched_dataset[period]):
                print(f"\n[{current_piece + 1}/{total_pieces}] Skipping (already processed): {art_piece.get('title', 'Unknown')} by {art_piece.get('artist', 'Unknown')}")
                current_piece += 1
                continue
            
            current_piece += 1
            title = art_piece.get('title', 'Unknown')
            artist = art_piece.get('artist', 'Unknown')
            
            print(f"\n[{current_piece}/{total_pieces}] Processing: {title} by {artist}")
            
            enriched_piece = enrich_art_piece_with_ai(client, art_piece)
            enriched_dataset[period].append(enriched_piece)
            
            # Print result if requested
            if print_results:
                print_artwork_result(enriched_piece)
            
            # Save after each artwork
            save_dataset(output_file, enriched_dataset)
            print(f"  ✓ Saved progress to {output_file}")
            
            # Rate limiting - be respectful to API
            time.sleep(1)  # 1 second delay between requests
    
    print(f"\n{'=' * 50}")
    print(f"✓ AI enrichment complete!")
    print(f"✓ Final dataset saved to {output_file}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    # Check for command-line argument to disable printing
    print_results = True
    if len(sys.argv) > 1 and sys.argv[1] in ['--no-print', '-n']:
        print_results = False
        print("Running in quiet mode (results will not be printed)")
    
    main(print_results=print_results)
