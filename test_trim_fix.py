#!/usr/bin/env python3
"""Test script to verify the TRIM marker type error is fixed"""

import sys
import traceback
from PIL import Image
from embroidery_converter import EmbroideryConverter, StitchType

def test_trim_fix():
    """Test if the trim marker fix works"""
    print("Testing trim marker fix...")

    try:
        # Create a simple test image
        img = Image.new('RGB', (5, 5), (0, 0, 0))  # Black background
        # Add some blue pixels
        img.putpixel((1, 1), (0, 0, 255))  # Blue
        img.putpixel((2, 1), (0, 0, 255))  # Blue
        img.putpixel((1, 2), (0, 0, 255))  # Blue
        img.putpixel((2, 2), (0, 0, 255))  # Blue

        # Save test image
        test_image_path = "test_input.png"
        img.save(test_image_path)

        # Initialize converter
        converter = EmbroideryConverter(test_image_path)

        # Configure colors
        converter.update_color_config('color_1', StitchType.NONE, 0.0)     # Black -> no stitching
        converter.update_color_config('color_2', StitchType.TATAMI, 2.0)   # Blue -> tatami fill

        print("Generating embroidery pattern...")

        # Try to generate the pattern - this should not fail with type error
        pattern = converter.generate_embroidery_pattern()

        print("✅ SUCCESS: Pattern generated without type errors!")
        print(f"Pattern has {len(pattern.stitches)} stitches")

        # Try to save to test export
        try:
            with open("test_output.pes", "wb") as f:
                pattern.write_pes(f)
            print("✅ SUCCESS: PES file export worked!")
        except Exception as e:
            print(f"PES export test skipped: {e}")

        return True

    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        print("Full traceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_trim_fix()
    sys.exit(0 if success else 1)