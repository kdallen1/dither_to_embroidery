#!/usr/bin/env python3
"""
Machine Embroidery Converter
Converts PNG images with 4 colors to DST embroidery files with customizable stitch types.
"""

import os
import json
import io
from PIL import Image, ImageDraw, ImageFont
import pyembroidery
import numpy as np
import webcolors
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

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

            # Generate descriptive thread color names based on actual RGB values
            color_name = self._get_thread_color_name(int(r), int(g), int(b))

            # Set default stitch types based on color characteristics
            brightness = (int(r) + int(g) + int(b)) / 3
            if brightness < 50:
                default_stitch = StitchType.FILL  # Dark colors good for fill
            elif brightness > 200:
                default_stitch = StitchType.NONE  # Light colors good for fabric
            else:
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

    def _get_thread_color_name(self, r: int, g: int, b: int) -> str:
        """Generate descriptive thread color name using webcolors"""
        try:
            # Ensure inputs are integers
            r, g, b = int(r), int(g), int(b)

            # Try to get the exact color name first
            closest_name = webcolors.rgb_to_name((r, g, b))
            return f"{closest_name.title()} Thread"
        except (ValueError, TypeError):
            # No exact match - find the closest named color from common thread colors
            try:
                r, g, b = int(r), int(g), int(b)

                # Common thread/embroidery colors
                common_colors = [
                    'black', 'white', 'gray', 'darkgray', 'lightgray',
                    'navy', 'darkblue', 'blue', 'lightblue', 'cyan',
                    'darkgreen', 'green', 'lime', 'lightgreen',
                    'darkred', 'red', 'pink', 'lightpink',
                    'purple', 'violet', 'magenta',
                    'brown', 'tan', 'beige',
                    'orange', 'gold', 'yellow', 'lightyellow'
                ]

                min_distance = float('inf')
                closest_color = 'Unknown'

                for color_name in common_colors:
                    try:
                        css_rgb = webcolors.name_to_rgb(color_name)
                        # Calculate Euclidean distance in RGB space
                        distance = sum((a - b) ** 2 for a, b in zip((r, g, b), css_rgb)) ** 0.5
                        if distance < min_distance:
                            min_distance = distance
                            closest_color = color_name
                    except:
                        continue

                return f"{closest_color.title()} Thread"
            except Exception as e:
                # Ultimate fallback
                return f"Color Thread RGB({r},{g},{b})"

    def group_adjacent_pixels(self, grouping_radius: int = 1) -> Dict[str, List[Tuple[int, int]]]:
        """Group adjacent same-color pixels into smart clusters while maintaining coverage"""
        if grouping_radius <= 1:
            return self.get_color_regions()  # No grouping

        grouped_regions = {key: [] for key in self.color_configs.keys()}
        processed = np.zeros((self.height, self.width), dtype=bool)

        for y in range(self.height):
            for x in range(self.width):
                if processed[y, x]:
                    continue

                pixel_color = tuple(self.pixels[y, x])
                if pixel_color not in self.color_mapping:
                    processed[y, x] = True
                    continue

                color_key = self.color_mapping[pixel_color]

                # Find connected component of same-color pixels
                region_pixels = self._find_connected_region(x, y, pixel_color, processed)

                if region_pixels:
                    # Instead of single center point, create a well-distributed set of points
                    representative_points = self._create_representative_points(region_pixels, grouping_radius)
                    grouped_regions[color_key].extend(representative_points)

        return grouped_regions

    def _find_connected_region(self, start_x: int, start_y: int, target_color: tuple,
                              processed: np.ndarray) -> List[Tuple[int, int]]:
        """Find all connected pixels of the same color using flood fill"""
        region = []
        stack = [(start_x, start_y)]

        while stack:
            x, y = stack.pop()

            # Check bounds and if already processed
            if (x < 0 or x >= self.width or y < 0 or y >= self.height or processed[y, x]):
                continue

            # Check if same color
            if tuple(self.pixels[y, x]) != target_color:
                continue

            # Mark as processed and add to region
            processed[y, x] = True
            region.append((x, y))

            # Add neighbors to stack
            stack.extend([(x+1, y), (x-1, y), (x, y+1), (x, y-1)])

        return region

    def _create_representative_points(self, region_pixels: List[Tuple[int, int]],
                                    grouping_radius: int) -> List[Tuple[int, int]]:
        """Create well-distributed representative points for a region"""
        if not region_pixels:
            return []

        # Be much more conservative - only group if we have many pixels
        if len(region_pixels) <= grouping_radius * 3:
            return region_pixels  # Keep all pixels for smaller regions

        # For larger regions, use smaller step size to maintain density
        # Find bounding box
        xs = [p[0] for p in region_pixels]
        ys = [p[1] for p in region_pixels]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Use much smaller step size to maintain coverage
        step = max(1, grouping_radius // 2)  # Half the radius for denser coverage
        region_set = set(region_pixels)  # For O(1) lookup
        representative_points = []

        for y in range(min_y, max_y + 1, step):
            for x in range(min_x, max_x + 1, step):
                if (x, y) in region_set:
                    representative_points.append((x, y))

        # If we still don't have enough points, use more points
        if len(representative_points) < len(region_pixels) // 2:
            # Use every 2nd or 3rd pixel instead of grid
            spacing = max(1, grouping_radius // 2)
            representative_points = region_pixels[::spacing]

        # Always ensure we have at least some reasonable coverage
        if len(representative_points) < len(region_pixels) // 3:
            representative_points = region_pixels

        return representative_points

    def _flood_fill_group(self, start_x: int, start_y: int, target_color: tuple,
                         max_radius: int, processed: np.ndarray) -> List[Tuple[int, int]]:
        """Flood fill to group adjacent same-color pixels within radius"""
        if processed[start_y, start_x]:
            return []

        group = []
        stack = [(start_x, start_y)]

        while stack:
            x, y = stack.pop()

            # Check bounds and if already processed
            if (x < 0 or x >= self.width or y < 0 or y >= self.height or
                processed[y, x]):
                continue

            # Check if same color
            if tuple(self.pixels[y, x]) != target_color:
                continue

            # Check if within radius from start point
            if abs(x - start_x) > max_radius or abs(y - start_y) > max_radius:
                continue

            # Add to group and mark as processed
            processed[y, x] = True
            group.append((x, y))

            # Add neighbors to stack
            stack.extend([(x+1, y), (x-1, y), (x, y+1), (x, y-1)])

        return group

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

    def generate_preview_image(self, scale_factor: int = 4,
                              use_grouping: bool = False, grouping_radius: int = 2) -> Image.Image:
        """Generate a visual preview of the stitch patterns"""
        # Create a preview image scaled up for better visibility
        preview_width = self.width * scale_factor
        preview_height = self.height * scale_factor

        # Create white background
        preview = Image.new('RGB', (preview_width, preview_height), 'white')
        draw = ImageDraw.Draw(preview)

        # Get color regions (with or without grouping)
        if use_grouping:
            regions = self.group_adjacent_pixels(grouping_radius)
        else:
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

            # Add color change with RGB color information
            if len(pattern.stitches) > 0:
                pattern.color_change()

            # Add thread color information to the pattern
            r, g, b = config.rgb
            pattern.add_thread({"color": (r << 16) | (g << 8) | b, "description": config.name})

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

    def export_pes(self, output_path: str):
        """Export the embroidery pattern as PES file"""
        pattern = self.generate_embroidery_pattern()
        pyembroidery.write_pes(pattern, output_path)
        print(f"PES file exported to: {output_path}")

    def export_pattern(self, output_path: str, format_type: str = 'dst'):
        """Export the embroidery pattern in specified format"""
        pattern = self.generate_embroidery_pattern()

        if format_type.lower() == 'dst':
            pyembroidery.write_dst(pattern, output_path)
        elif format_type.lower() == 'pes':
            pyembroidery.write_pes(pattern, output_path)
        else:
            raise ValueError(f"Unsupported format: {format_type}")

        print(f"{format_type.upper()} file exported to: {output_path}")

    def export_pdf_preview(self, output_path: str):
        """Export a PDF with thread color preview and pattern information"""
        # Create PDF canvas
        pdf = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter

        # Title
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(50, height - 50, "Embroidery Pattern Preview")

        # Pattern info
        pdf.setFont("Helvetica", 12)
        y_pos = height - 90
        pdf.drawString(50, y_pos, f"Image size: {self.width} x {self.height} pixels")

        # Thread color information
        y_pos -= 40
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(50, y_pos, "Thread Colors:")

        y_pos -= 25
        pdf.setFont("Helvetica", 12)
        for color_key, config in self.color_configs.items():
            if config.stitch_type == StitchType.NONE:
                continue

            r, g, b = config.rgb

            # Draw color swatch
            pdf.setFillColor(colors.Color(r/255, g/255, b/255))
            pdf.rect(50, y_pos - 8, 20, 15, fill=1, stroke=1)

            # Draw color info
            pdf.setFillColor(colors.black)
            pdf.drawString(80, y_pos, f"{config.name} - RGB({r}, {g}, {b}) - {config.stitch_type.value.capitalize()} stitch")
            y_pos -= 25

        # Add preview image
        try:
            # Generate preview image
            preview_img = self.generate_preview_image(scale_factor=6)

            # Convert to format suitable for PDF
            img_buffer = io.BytesIO()
            preview_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)

            # Add image to PDF
            img = ImageReader(img_buffer)
            img_width = min(400, width - 100)  # Max width 400px, with margins
            img_height = (preview_img.height * img_width) // preview_img.width

            if y_pos - img_height < 100:  # Start new page if not enough space
                pdf.showPage()
                y_pos = height - 50
                pdf.setFont("Helvetica-Bold", 14)
                pdf.drawString(50, y_pos, "Pattern Preview:")
                y_pos -= 30

            pdf.drawImage(img, 50, y_pos - img_height, width=img_width, height=img_height)

        except Exception as e:
            pdf.drawString(50, y_pos - 30, f"Preview image error: {str(e)}")

        # Statistics
        regions = self.get_color_regions()
        total_stitches = sum(len(points) for points in regions.values())

        pdf.showPage()  # New page for stats
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, height - 50, "Pattern Statistics")

        y_pos = height - 90
        pdf.setFont("Helvetica", 12)
        pdf.drawString(50, y_pos, f"Total stitch points: {total_stitches:,}")

        y_pos -= 20
        for color_key, config in self.color_configs.items():
            if config.stitch_type == StitchType.NONE:
                continue
            points = regions[color_key]
            pdf.drawString(50, y_pos, f"{config.name}: {len(points):,} stitches")
            y_pos -= 15

        pdf.save()
        print(f"PDF preview exported to: {output_path}")

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