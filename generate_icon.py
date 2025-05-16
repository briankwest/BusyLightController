#!/usr/bin/env python3
# Script to generate a Windows ICO file from PNG
# Requires pillow: pip install pillow

from PIL import Image
import os

def create_icon_file():
    """Create an ICO file from the PNG icon"""
    print("Generating Windows ICO file from icon.png...")
    
    if not os.path.exists("icon.png"):
        print("icon.png not found - creating default icon")
        # Create a new image with a green background (default)
        img = Image.new("RGB", (256, 256), color=(0, 255, 0))
        img.save("icon.png")
    
    # Open the source image
    img = Image.open("icon.png")
    
    # Create different sizes for the ico
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Resize the image to each size
    resized_images = [img.resize(size) for size in sizes]
    
    # Save as ICO with multiple sizes
    img.save("icon.ico", format="ICO", sizes=[(img.size[0], img.size[1], img.size[0], img.size[1])])
    
    print("icon.ico created successfully")

if __name__ == "__main__":
    try:
        create_icon_file()
    except Exception as e:
        print(f"Error creating icon: {e}")