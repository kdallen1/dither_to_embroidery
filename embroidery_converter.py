#!/usr/bin/env python3
"""
Machine Embroidery Converter
Converts PNG images with 4 colors to DST embroidery files with customizable stitch types.
"""

import os
import json
from PIL import Image, ImageDraw, ImageFont
import pyembroidery
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class StitchType(Enum):
    NONE = "none"
    FILL = "fill"
    CROSS = "cross"
    RUNNING = "running"

@dataclass
class ColorConfig:
    name: str
    rgb: Tuple[int, int, int]
    stitch_type: StitchType
    pixel_size: float  # Size in mm for each "pixel"

class EmbroideryConverter:
    def __init__(self, image_path: str):
        self.image_path = image_path
        self.image = Image.open(image_path).convert('RGB')
        self.width, self.height = self.image.size
        self.pixels = np.array(self.image)

        # Auto-detect colors and create configurations
        self.color_configs = {}
        self._analyze_colors()

    def _analyze_colors(self):
        """Analyze image to find unique colors and create configurations"""
        # Get unique colors
        pixels_2d = self.pixels.reshape(-1, 3)
        unique_colors = np.unique(pixels_2d, axis=0)

        print(f"Found {len(unique_colors)} unique colors in image:")

        # Create a configuration for each detected color
        color_mapping = {}
        for i, color in enumerate(unique_colors):
            r, g, b = color
            print(f"  Color {i+1}: RGB({r}, {g}, {b})")

            # Generate a unique key for this color
            color_key = f"color_{i+1}"

            # Generate a descriptive name based on color characteristics
            brightness = (int(r) + int(g) + int(b)) / 3
            if brightness < 50:
                color_name = f"Dark Color {i+1}"
                default_stitch = StitchType.FILL  # Dark colors good for fill
            elif brightness > 200:
                color_name = f"Light Color {i+1}"
                default_stitch = StitchType.NONE  # Light colors good for fabric
            else:
                color_name = f"Color {i+1}"
                default_stitch = StitchType.CROSS  # Medium colors good for cross stitch

            # Create configuration
            self.color_configs[color_key] = ColorConfig(
                name=color_name,
                rgb=(int(r), int(g), int(b)),
                stitch_type=default_stitch,
                pixel_size=2.0
            )

            color_mapping[tuple(color)] = color_key

        self.color_mapping = color_mapping

    def get_color_regions(self) -> Dict[str, List[Tuple[int, int]]]:
        """Extract pixel coordinates for each color"""
        regions = {key: [] for key in self.color_configs.keys()}

        for y in range(self.height):
            for x in range(self.width):
                pixel_color = tuple(self.pixels[y, x])
                if pixel_color in self.color_mapping:
                    color_key = self.color_mapping[pixel_color]
                    regions[color_key].append((x, y))

        return regions

    def update_color_config(self, color_key: str, stitch_type: StitchType, pixel_size: float):
        """Update stitch configuration for a color"""
        if color_key in self.color_configs:
            self.color_configs[color_key].stitch_type = stitch_type
            self.color_configs[color_key].pixel_size = pixel_size

    def generate_fill_stitch(self, points: List[Tuple[int, int]], pixel_size: float) -> List[Tuple[float, float]]:
        """Generate fill stitch pattern for connected regions"""
        if not points:
            return []

        # Convert pixel coordinates to mm (0.1mm units for DST)
        mm_points = [(x * pixel_size * 10, y * pixel_size * 10) for x, y in points]

        # Simple fill: horizontal lines back and forth
        stitches = []

        # Group points by Y coordinate
        y_groups = {}
        for x, y in mm_points:
            y_int = int(y)
            if y_int not in y_groups:
                y_groups[y_int] = []
            y_groups[y_int].append(x)

        # Create horizontal fill lines
        for y in sorted(y_groups.keys()):
            x_coords = sorted(y_groups[y])
            if len(x_coords) >= 2:
                # Fill from min to max X
                min_x, max_x = min(x_coords), max(x_coords)

                # Alternate direction for each line
                if len(stitches) % 2 == 0:
                    # Left to right
                    for x in range(int(min_x), int(max_x) + 1, 20):  # 2mm spacing
                        stitches.append((x, y))
                else:
                    # Right to left
                    for x in range(int(max_x), int(min_x) - 1, -20):
                        stitches.append((x, y))

        return stitches

    def generate_cross_stitch(self, points: List[Tuple[int, int]], pixel_size: float) -> List[Tuple[float, float]]:
        """Generate cross stitch pattern"""
        if not points:
            return []

        stitches = []
        pixel_size_mm = pixel_size * 10  # Convert to 0.1mm units

        for x, y in points:
            # Convert to mm coordinates
            center_x = x * pixel_size_mm
            center_y = y * pixel_size_mm

            # Create cross pattern (4 stitches forming an X)
            half_size = pixel_size_mm // 2

            # First diagonal: top-left to bottom-right
            stitches.append((center_x - half_size, center_y - half_size))
            stitches.append((center_x + half_size, center_y + half_size))

            # Second diagonal: top-right to bottom-left
            stitches.append((center_x + half_size, center_y - half_size))
            stitches.append((center_x - half_size, center_y + half_size))

        return stitches

    def generate_preview_image(self, scale_factor: int = 4) -> Image.Image:
        """Generate a visual preview of the stitch patterns"""
        # Create a preview image scaled up for better visibility
        preview_width = self.width * scale_factor
        preview_height = self.height * scale_factor

        # Create white background
        preview = Image.new('RGB', (preview_width, preview_height), 'white')
        draw = ImageDraw.Draw(preview)

        # Get color regions
        regions = self.get_color_regions()

        for color_key, config in self.color_configs.items():
            points = regions[color_key]
            if not points or config.stitch_type == StitchType.NONE:
                continue

            # Use the actual detected color for drawing
            thread_color = config.rgb

            for x, y in points:
                # Scale up the coordinates
                scaled_x = x * scale_factor
                scaled_y = y * scale_factor

                if config.stitch_type == StitchType.FILL:
                    # Draw filled squares for fill stitch
                    draw.rectangle([
                        scaled_x, scaled_y,
                        scaled_x + scale_factor - 1, scaled_y + scale_factor - 1
                    ], fill=thread_color)

                elif config.stitch_type == StitchType.CROSS:
                    # Draw X pattern for cross stitch with bright, visible colors
                    center_x = scaled_x + scale_factor // 2
                    center_y = scaled_y + scale_factor // 2
                    offset = max(scale_factor // 2 - 1, 1)  # Bigger cross pattern

                    # Use brighter versions of the thread colors for better visibility
                    if thread_color == (20, 16, 108):  # Dark blue -> bright blue
                        bright_color = (0, 100, 255)
                    elif thread_color == (24, 135, 87):  # Dark green -> bright green
                        bright_color = (0, 200, 100)
                    else:
                        bright_color = thread_color

                    # Draw thicker X with bright colors
                    line_width = max(scale_factor // 2, 2)
                    draw.line([
                        center_x - offset, center_y - offset,
                        center_x + offset, center_y + offset
                    ], fill=bright_color, width=line_width)
                    draw.line([
                        center_x + offset, center_y - offset,
                        center_x - offset, center_y + offset
                    ], fill=bright_color, width=line_width)

                elif config.stitch_type == StitchType.RUNNING:
                    # Draw dots for running stitch
                    center_x = scaled_x + scale_factor // 2
                    center_y = scaled_y + scale_factor // 2
                    radius = scale_factor // 4

                    draw.ellipse([
                        center_x - radius, center_y - radius,
                        center_x + radius, center_y + radius
                    ], fill=thread_color)

        return preview

    def save_preview_image(self, output_path: str, scale_factor: int = 4):
        """Save the preview image to a file"""
        preview = self.generate_preview_image(scale_factor)
        preview.save(output_path)
        print(f"Preview image saved to: {output_path}")

    def generate_embroidery_pattern(self) -> pyembroidery.EmbPattern:
        """Generate the complete embroidery pattern"""
        pattern = pyembroidery.EmbPattern()

        # Get color regions
        regions = self.get_color_regions()

        # Process each color
        for color_key, config in self.color_configs.items():
            if config.stitch_type == StitchType.NONE:
                continue  # Skip colors with no stitch

            points = regions[color_key]
            if not points:
                continue

            # Add color change
            if len(pattern.stitches) > 0:
                pattern.color_change()

            # Generate stitches based on type
            if config.stitch_type == StitchType.FILL:
                stitches = self.generate_fill_stitch(points, config.pixel_size)
            elif config.stitch_type == StitchType.CROSS:
                stitches = self.generate_cross_stitch(points, config.pixel_size)
            else:
                continue  # Skip unknown stitch types

            # Add stitches to pattern
            if stitches:
                # Move to first point
                pattern.move_abs(stitches[0][0], stitches[0][1])

                # Add remaining stitches
                for x, y in stitches[1:]:
                    pattern.stitch_abs(x, y)

        pattern.end()
        return pattern

    def export_dst(self, output_path: str):
        """Export the embroidery pattern as DST file"""
        pattern = self.generate_embroidery_pattern()
        pyembroidery.write_dst(pattern, output_path)
        print(f"DST file exported to: {output_path}")

    def get_config_json(self) -> str:
        """Get current configuration as JSON for UI"""
        config_dict = {}
        for key, config in self.color_configs.items():
            config_dict[key] = {
                'name': config.name,
                'rgb': config.rgb,
                'stitch_type': config.stitch_type.value,
                'pixel_size': config.pixel_size
            }
        return json.dumps(config_dict, indent=2)

# Example usage
if __name__ == "__main__":
    # Test with the horse image
    converter = EmbroideryConverter("leftys_horses_tag_bg.png")

    # Print current configuration
    print("\nCurrent Configuration:")
    print(converter.get_config_json())

    # Generate and export DST file
    converter.export_dst("horses_embroidery.dst")

    # Print some statistics
    regions = converter.get_color_regions()
    print("\nColor Statistics:")
    for color_key, points in regions.items():
        config = converter.color_configs[color_key]
        print(f"  {config.name}: {len(points)} pixels, stitch type: {config.stitch_type.value}")