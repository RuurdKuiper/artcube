#!/usr/bin/env python3
"""
Resize images to be at most 1 MB in size.
Maintains aspect ratio and quality.
"""

import os
from PIL import Image
from pathlib import Path

def get_file_size_mb(filepath):
    """Get file size in MB."""
    return os.path.getsize(filepath) / (1024 * 1024)

def resize_image_to_max_size(image_path, max_size_mb=1.0, max_dimension=2000):
    """Resize image to be at most max_size_mb MB, maintaining aspect ratio."""
    try:
        # Convert Path to string if needed
        image_path_str = str(image_path)
        
        # Get current file size
        current_size_mb = get_file_size_mb(image_path_str)
        
        if current_size_mb <= max_size_mb:
            print(f"  ✓ {os.path.basename(image_path_str)}: {current_size_mb:.2f} MB (OK)")
            return False
        
        print(f"  Resizing {os.path.basename(image_path_str)}: {current_size_mb:.2f} MB -> ", end="", flush=True)
        
        # Open image
        with Image.open(image_path_str) as img:
            # Convert to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            original_size = img.size
            original_format = img.format
            
            # Calculate new dimensions
            width, height = img.size
            quality = 85
            
            # If file is extremely large, aggressively reduce dimensions first
            if current_size_mb > 10:
                # For very large files, start with smaller max dimension
                aggressive_max_dim = 1200
                if max(width, height) > aggressive_max_dim:
                    if width > height:
                        new_width = aggressive_max_dim
                        new_height = int(height * (aggressive_max_dim / width))
                    else:
                        new_height = aggressive_max_dim
                        new_width = int(width * (aggressive_max_dim / height))
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    print(f"resized to {new_width}x{new_height}, ", end="", flush=True)
            elif max(width, height) > max_dimension:
                # For moderately large files, use max_dimension
                if width > height:
                    new_width = max_dimension
                    new_height = int(height * (max_dimension / width))
                else:
                    new_height = max_dimension
                    new_width = int(width * (max_dimension / height))
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(f"resized to {new_width}x{new_height}, ", end="", flush=True)
            
            # Save with decreasing quality until we're under the size limit
            temp_path = image_path_str + '.tmp'
            attempts = 0
            max_attempts = 20
            
            while attempts < max_attempts:
                img.save(temp_path, format='JPEG', quality=quality, optimize=True)
                new_size_mb = get_file_size_mb(temp_path)
                
                if new_size_mb <= max_size_mb:
                    break
                
                # If still too large, reduce dimensions further
                if attempts > 5 and new_size_mb > max_size_mb * 1.5:
                    width, height = img.size
                    img = img.resize((int(width * 0.9), int(height * 0.9)), Image.Resampling.LANCZOS)
                    print(f"further reduced, ", end="", flush=True)
                
                quality = max(50, quality - 5)
                attempts += 1
            
            # Replace original with resized version
            os.replace(temp_path, image_path_str)
            new_size_mb = get_file_size_mb(image_path_str)
            print(f"{new_size_mb:.2f} MB (quality: {quality}%)")
            
            return True
            
    except Exception as e:
        print(f"  ✗ Error processing {os.path.basename(str(image_path))}: {e}")
        temp_path = str(image_path) + '.tmp'
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def main():
    images_dir = Path("images")
    
    if not images_dir.exists():
        print(f"Images directory '{images_dir}' not found!")
        return
    
    # Find all image files
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    image_files = []
    for ext in image_extensions:
        image_files.extend(images_dir.glob(f"*{ext}"))
        image_files.extend(images_dir.glob(f"*{ext.upper()}"))
    
    if not image_files:
        print("No images found!")
        return
    
    print(f"Found {len(image_files)} images")
    print(f"Resizing images larger than 1 MB...\n")
    
    resized_count = 0
    total_original_size = 0
    total_new_size = 0
    
    for image_path in sorted(image_files):
        original_size = get_file_size_mb(image_path)
        total_original_size += original_size
        
        if resize_image_to_max_size(image_path):
            resized_count += 1
        
        total_new_size += get_file_size_mb(image_path)
    
    print(f"\nSummary:")
    print(f"  Total images: {len(image_files)}")
    print(f"  Resized: {resized_count}")
    print(f"  Original total size: {total_original_size:.2f} MB")
    print(f"  New total size: {total_new_size:.2f} MB")
    print(f"  Space saved: {total_original_size - total_new_size:.2f} MB")

if __name__ == "__main__":
    main()
