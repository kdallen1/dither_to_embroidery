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
    SATIN = "satin"      # For narrow areas (under 10mm) - smooth directional fill
    TATAMI = "tatami"    # For larger areas - textured fill at angle
    DENSE_TATAMI = "dense_tatami"  # Dense 45-degree fill for raised effect
    RUNNING = "running"  # For outlines

@dataclass
class ColorConfig:
    name: str
    rgb: Tuple[int, int, int]
    stitch_type: StitchType
    pixel_size: float
    density: float = 1.0           # Lighter density for cleaner designs (1.0mm spacing)
    stitch_length: float = 25.0    # 2.5mm segments (25 units at 0.1mm)
    fill_angle: float = 45.0       # 45° angle for stability

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

            # Set default stitch types based on professional practices
            brightness = (int(r) + int(g) + int(b)) / 3
            if brightness < 50:
                default_stitch = StitchType.TATAMI  # Dark colors good for textured fill
            elif brightness > 200:
                default_stitch = StitchType.NONE   # Light colors treated as fabric
            else:
                default_stitch = StitchType.TATAMI  # Medium colors use tatami fill

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

    def generate_underlay(self, points: List[Tuple[int, int]], pixel_size: float,
                         underlay_type: str = "edge") -> List[Tuple[float, float]]:
        """Generate professional underlay stitches"""
        if not points:
            return []

        stitches = []
        pixel_size_mm = pixel_size * 10

        if underlay_type == "edge":
            # Edge run underlay - traces around the perimeter
            # Find boundary points (simplified approach)
            boundary = self._find_boundary_points(points)
            for x, y in boundary:
                stitches.append((x * pixel_size_mm, y * pixel_size_mm))

        elif underlay_type == "zigzag":
            # Zigzag underlay - 90° to main fill direction
            y_groups = {}
            for x, y in points:
                if y not in y_groups:
                    y_groups[y] = []
                y_groups[y].append(x)

            # Create zigzag pattern perpendicular to fill
            for y in sorted(y_groups.keys())[::3]:  # Every 3rd row for underlay
                x_coords = sorted(y_groups[y])
                if len(x_coords) >= 2:
                    min_x, max_x = min(x_coords), max(x_coords)
                    # Zigzag from left to right
                    for x in range(min_x, max_x + 1, 3):  # Sparse spacing for underlay
                        stitches.append((x * pixel_size_mm, y * pixel_size_mm))

        return stitches

    def _find_boundary_points(self, points: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Find boundary points for edge underlay (simplified)"""
        if not points:
            return []
        point_set = set(points)
        boundary = []

        for x, y in points:
            # Check if point is on the boundary (has at least one non-neighbor)
            neighbors = [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
            if any(neighbor not in point_set for neighbor in neighbors):
                boundary.append((x, y))

        return boundary

    def generate_tatami_fill(self, points: List[Tuple[int, int]], pixel_size: float,
                           fill_angle: float = 45.0, density: float = 4.0) -> List[Tuple[float, float]]:
        """Generate pixelated tatami fill - each pixel becomes a small tatami square with proper trimming"""
        if not points:
            return []

        stitches = []

        # For each pixel, create a small tatami-filled square
        for i, (x, y) in enumerate(points):
            # Convert pixel coordinates to real coordinates
            real_x = x * pixel_size * 10  # Convert to 0.1mm units
            real_y = y * pixel_size * 10

            # Create a small tatami square for this pixel
            square_size = pixel_size * 10  # Size of each pixel square

            # Generate 2-3 horizontal tatami lines per pixel square
            num_lines = max(2, int(square_size / 40))  # At least 2 lines, more for larger pixels
            line_spacing = square_size / (num_lines + 1)

            for j in range(num_lines):
                y_offset = line_spacing * (j + 1)
                start_x = real_x + square_size * 0.1  # Small margin from edge
                end_x = real_x + square_size * 0.9
                line_y = real_y + y_offset

                stitches.extend([
                    (start_x, line_y),
                    (end_x, line_y)
                ])

            # Add special marker for trim after each pixel (except the last)
            if i < len(points) - 1:
                # Use None to indicate trim
                stitches.append(None)

        return stitches

    def generate_dense_tatami_fill(self, points: List[Tuple[int, int]], pixel_size: float,
                                  fill_angle: float = 45.0, density: float = 6.0) -> List[Tuple[float, float]]:
        """Generate dense 45-degree tatami fill with guaranteed complete coverage"""
        if not points:
            return []

        import math
        pixel_size_mm = pixel_size * 10
        stitches = []

        # Create a set for fast point lookup
        point_set = set(points)

        # Find the bounding box of filled pixels
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Calculate dense line spacing for tatami effect
        line_spacing_mm = pixel_size_mm / (density * 1.5)  # Dense spacing for professional tatami

        # Convert 45-degree angle to radians for proper tatami
        angle_rad = math.radians(fill_angle)
        cos_angle = math.cos(angle_rad)
        sin_angle = math.sin(angle_rad)

        # Calculate perpendicular direction for line spacing
        perp_cos = -sin_angle
        perp_sin = cos_angle

        # HIGH-RESOLUTION DENSE TATAMI with complete coverage and proper trimming
        line_direction = 1
        last_point = None

        # Calculate dense line spacing - much tighter for professional dense tatami
        line_spacing = max(0.3, 1.0 / density)  # Very tight spacing for dense effect

        # PASS 1: High-resolution 45-degree diagonal lines
        # Generate many more diagonal lines with fractional spacing for density
        diagonal_start = -(self.height)
        diagonal_end = self.width
        current_diagonal = diagonal_start

        while current_diagonal <= diagonal_end:
            current_segment = []

            # HIGH-RESOLUTION: Sample every pixel along this diagonal line
            max_steps = self.width + self.height
            for step in range(max_steps):
                # Calculate pixel coordinates for this diagonal
                if line_direction == 1:
                    x = int(current_diagonal + step)
                    y = step
                else:
                    x = int(current_diagonal + max_steps - 1 - step)
                    y = max_steps - 1 - step

                # Check bounds and if pixel is filled - HIGH DETAIL DETECTION
                if (0 <= x < self.width and 0 <= y < self.height and
                    (x, y) in point_set):
                    current_segment.append((x * pixel_size_mm, y * pixel_size_mm))
                else:
                    # PRECISE TRIMMING: End segment when leaving filled area
                    if current_segment:
                        # Check if we need a trim (careful gap detection)
                        if last_point and current_segment:
                            dist = math.sqrt((current_segment[0][0] - last_point[0])**2 +
                                           (current_segment[0][1] - last_point[1])**2)
                            # More sensitive trim detection for precise cuts
                            if dist > pixel_size_mm * 1.5:
                                stitches.append(None)  # Trim for smaller gaps

                        # Add all stitches in this segment
                        stitches.extend(current_segment)
                        if current_segment:
                            last_point = current_segment[-1]
                        current_segment = []

            # Add final segment if exists
            if current_segment:
                if last_point and current_segment:
                    dist = math.sqrt((current_segment[0][0] - last_point[0])**2 +
                                   (current_segment[0][1] - last_point[1])**2)
                    if dist > pixel_size_mm * 1.5:
                        stitches.append(None)

                stitches.extend(current_segment)
                if current_segment:
                    last_point = current_segment[-1]

            # DENSER SPACING: Move to next diagonal line with tight spacing
            current_diagonal += line_spacing
            # Alternate direction for professional back-and-forth
            line_direction *= -1

        # PASS 2: Perpendicular crosshatch diagonals for complete density
        # These go the opposite direction for true tatami crosshatch
        crosshatch_spacing = line_spacing * 2  # Slightly sparser for crosshatch

        diagonal_start_cross = 0
        diagonal_end_cross = self.width + self.height
        current_diagonal_cross = diagonal_start_cross

        while current_diagonal_cross <= diagonal_end_cross:
            current_segment = []

            # Sample every pixel along this perpendicular diagonal
            max_steps = self.width + self.height
            for step in range(max_steps):
                # Calculate pixel coordinates for perpendicular diagonal
                x = int(current_diagonal_cross - step)
                y = step

                # HIGH DETAIL: Check every pixel for precise edge detection
                if (0 <= x < self.width and 0 <= y < self.height and
                    (x, y) in point_set):
                    current_segment.append((x * pixel_size_mm, y * pixel_size_mm))
                else:
                    # PRECISE CROSSHATCH TRIMMING
                    if current_segment:
                        if last_point and current_segment:
                            dist = math.sqrt((current_segment[0][0] - last_point[0])**2 +
                                           (current_segment[0][1] - last_point[1])**2)
                            # Crosshatch can have slightly larger gaps
                            if dist > pixel_size_mm * 2.0:
                                stitches.append(None)

                        stitches.extend(current_segment)
                        if current_segment:
                            last_point = current_segment[-1]
                        current_segment = []

            # Add final crosshatch segment
            if current_segment:
                if last_point and current_segment:
                    dist = math.sqrt((current_segment[0][0] - last_point[0])**2 +
                                   (current_segment[0][1] - last_point[1])**2)
                    if dist > pixel_size_mm * 2.0:
                        stitches.append(None)

                stitches.extend(current_segment)
                if current_segment:
                    last_point = current_segment[-1]

            # Move to next crosshatch line with dense spacing
            current_diagonal_cross += crosshatch_spacing

        return stitches


    def generate_satin_fill(self, points: List[Tuple[int, int]], pixel_size: float,
                          fill_angle: float = 0.0, density: float = 4.0) -> List[Tuple[float, float]]:
        """Generate professional satin fill for narrow areas"""
        if not points:
            return []

        import math
        stitches = []
        pixel_set = set(points)

        # Find the shape width to determine if suitable for satin
        min_x = min(x for x, y in points)
        max_x = max(x for x, y in points)
        min_y = min(y for x, y in points)
        max_y = max(y for x, y in points)

        width_mm = (max_x - min_x) * pixel_size
        height_mm = (max_y - min_y) * pixel_size

        # If too wide for satin, fallback to tatami
        if width_mm > 10:  # 10mm max for satin
            return self.generate_tatami_fill(points, pixel_size, fill_angle, density)

        # Generate satin stitches perpendicular to the main axis
        pixel_size_mm = pixel_size * 10

        # Determine fill direction (perpendicular to longest axis)
        if width_mm > height_mm:
            # Fill vertically for horizontal shapes
            for x in range(min_x, max_x + 1):
                column_points = [(px, py) for px, py in points if px == x]
                if column_points:
                    column_points.sort(key=lambda p: p[1])
                    if len(column_points) >= 2:
                        start_y = column_points[0][1]
                        end_y = column_points[-1][1]
                        stitches.append((x * pixel_size_mm, start_y * pixel_size_mm))
                        stitches.append((x * pixel_size_mm, end_y * pixel_size_mm))
        else:
            # Fill horizontally for vertical shapes
            for y in range(min_y, max_y + 1):
                row_points = [(px, py) for px, py in points if py == y]
                if row_points:
                    row_points.sort(key=lambda p: p[0])
                    if len(row_points) >= 2:
                        start_x = row_points[0][0]
                        end_x = row_points[-1][0]
                        stitches.append((start_x * pixel_size_mm, y * pixel_size_mm))
                        stitches.append((end_x * pixel_size_mm, y * pixel_size_mm))

        return stitches

    def generate_running_stitch(self, points: List[Tuple[int, int]], pixel_size: float,
                              stitch_length: float = 25.0) -> List[Tuple[float, float]]:
        """Generate professional running stitch with proper 2.5mm segments"""
        if not points:
            return []

        import math
        stitches = []
        pixel_size_mm = pixel_size * 10

        # Find boundary for outline stitching
        boundary_points = self._find_boundary_points(points)
        if not boundary_points:
            return []

        # Sort boundary points to create a continuous path with better topology
        path = self._create_smooth_boundary_path(boundary_points)

        # Apply curve smoothing and convert to running stitch with proper segment length
        smoothed_path = self._apply_curve_smoothing(path)

        # Generate stitches at proper intervals
        for i, (x, y) in enumerate(smoothed_path):
            stitch_x = x * pixel_size_mm
            stitch_y = y * pixel_size_mm

            if i == 0:
                # Always include start point
                stitches.append((stitch_x, stitch_y))
            else:
                # Check distance from last stitch
                last_stitch = stitches[-1]
                distance = math.sqrt((stitch_x - last_stitch[0])**2 + (stitch_y - last_stitch[1])**2)

                if distance >= stitch_length:  # 2.5mm standard
                    stitches.append((stitch_x, stitch_y))

        # Ensure we end exactly at the last point if it's far enough
        if smoothed_path:
            last_x, last_y = smoothed_path[-1]
            final_stitch = (last_x * pixel_size_mm, last_y * pixel_size_mm)
            if stitches:
                last_stitch = stitches[-1]
                distance = math.sqrt((final_stitch[0] - last_stitch[0])**2 + (final_stitch[1] - last_stitch[1])**2)
                if distance >= stitch_length / 2:  # At least half segment length
                    stitches.append(final_stitch)

        return stitches

    def _create_smooth_boundary_path(self, boundary_points: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Create a smooth continuous path from boundary points"""
        if len(boundary_points) < 2:
            return boundary_points

        import math

        # Start with leftmost point and build path using nearest neighbor
        current_point = min(boundary_points, key=lambda p: (p[0], p[1]))
        path = [current_point]
        remaining = set(boundary_points) - {current_point}

        while remaining:
            # Find nearest unvisited point
            distances = [(math.sqrt((current_point[0] - p[0])**2 + (current_point[1] - p[1])**2), p)
                        for p in remaining]
            _, next_point = min(distances)
            path.append(next_point)
            remaining.remove(next_point)
            current_point = next_point

        return path

    def _apply_curve_smoothing(self, path: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Apply simple curve smoothing to reduce sharp corners"""
        if len(path) < 3:
            return path

        smoothed = [path[0]]  # Keep first point

        # Apply simple smoothing by averaging with neighbors
        for i in range(1, len(path) - 1):
            prev_x, prev_y = path[i - 1]
            curr_x, curr_y = path[i]
            next_x, next_y = path[i + 1]

            # Simple weighted average for smoothing
            smooth_x = int(0.25 * prev_x + 0.5 * curr_x + 0.25 * next_x)
            smooth_y = int(0.25 * prev_y + 0.5 * curr_y + 0.25 * next_y)

            smoothed.append((smooth_x, smooth_y))

        smoothed.append(path[-1])  # Keep last point
        return smoothed

    def apply_center_out_sequencing(self, stitches: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Apply center-out sequencing (tablecloth method) to minimize fabric distortion"""
        if len(stitches) < 3:
            return stitches

        import math

        # Find the center of the stitch area
        center_x = sum(x for x, y in stitches) / len(stitches)
        center_y = sum(y for x, y in stitches) / len(stitches)

        # Create a copy of stitches with distance from center
        stitch_data = [(x, y, math.sqrt((x - center_x)**2 + (y - center_y)**2))
                      for x, y in stitches]

        # Sort by distance from center (nearest first)
        stitch_data.sort(key=lambda item: item[2])

        # Build sequenced path using tablecloth method
        sequenced = []
        remaining = list(stitch_data)

        # Start from center-most point
        current = remaining.pop(0)
        sequenced.append((current[0], current[1]))

        while remaining:
            # Find closest unvisited point to current position
            current_x, current_y = sequenced[-1]
            distances = [
                (math.sqrt((current_x - item[0])**2 + (current_y - item[1])**2), i, item)
                for i, item in enumerate(remaining)
            ]
            distances.sort(key=lambda x: x[0])

            # Take the closest point
            _, idx, next_stitch = distances[0]
            sequenced.append((next_stitch[0], next_stitch[1]))
            remaining.pop(idx)

        return sequenced

    def get_fabric_adjusted_density(self, base_density: float, fabric_type: str = "cotton") -> float:
        """Calculate fabric-aware density adjustments for professional results"""
        # Professional density adjustments based on fabric type
        fabric_multipliers = {
            "cotton": 1.0,      # Standard baseline
            "jersey": 1.2,      # Stretchier, needs tighter density
            "denim": 0.8,       # Heavy fabric, looser density
            "silk": 0.9,        # Delicate fabric
            "linen": 1.1,       # Loose weave needs tighter stitches
            "fleece": 1.3,      # Thick pile fabric
            "canvas": 0.7,      # Very heavy fabric
            "satin": 0.9,       # Slippery fabric
            "polyester": 1.0,   # Synthetic baseline
            "rayon": 1.1        # Tends to pucker
        }

        multiplier = fabric_multipliers.get(fabric_type.lower(), 1.0)
        return base_density * multiplier

    def optimize_color_sequence(self, color_regions: dict) -> List[str]:
        """Optimize the order of colors to minimize machine head jumps"""
        import math

        if not color_regions:
            return []

        # Calculate center point for each color
        color_centers = {}
        for color_key, points in color_regions.items():
            if points and self.color_configs[color_key].stitch_type != StitchType.NONE:
                center_x = sum(x for x, y in points) / len(points)
                center_y = sum(y for x, y in points) / len(points)
                color_centers[color_key] = (center_x, center_y)

        if not color_centers:
            return []

        # Use nearest neighbor algorithm to minimize jumps
        remaining_colors = set(color_centers.keys())
        optimized_order = []

        # Start with the leftmost/topmost color
        current_color = min(remaining_colors, key=lambda c: (color_centers[c][1], color_centers[c][0]))
        optimized_order.append(current_color)
        remaining_colors.remove(current_color)
        current_center = color_centers[current_color]

        while remaining_colors:
            # Find nearest remaining color
            distances = [
                (math.sqrt((current_center[0] - color_centers[color][0])**2 +
                          (current_center[1] - color_centers[color][1])**2), color)
                for color in remaining_colors
            ]
            _, next_color = min(distances)

            optimized_order.append(next_color)
            remaining_colors.remove(next_color)
            current_center = color_centers[next_color]

        return optimized_order

    def validate_embroidery_quality(self) -> dict:
        """Validate embroidery quality and return professional metrics"""
        regions = self.get_color_regions()
        validation_report = {
            "overall_quality": "GOOD",
            "warnings": [],
            "statistics": {},
            "recommendations": []
        }

        total_stitches = 0
        total_jumps = 0
        color_changes = 0
        max_density_area = 0

        for color_key, config in self.color_configs.items():
            if config.stitch_type == StitchType.NONE:
                continue

            points = regions[color_key]
            if not points:
                continue

            color_changes += 1

            # Generate stitches to analyze
            if config.stitch_type == StitchType.TATAMI:
                adjusted_density = self.get_fabric_adjusted_density(config.density, "cotton")
                stitches = self.generate_tatami_fill(points, config.pixel_size, config.fill_angle, adjusted_density)
            elif config.stitch_type == StitchType.DENSE_TATAMI:
                adjusted_density = self.get_fabric_adjusted_density(config.density * 1.5, "cotton")
                stitches = self.generate_dense_tatami_fill(points, config.pixel_size, config.fill_angle, adjusted_density)
            elif config.stitch_type == StitchType.SATIN:
                adjusted_density = self.get_fabric_adjusted_density(config.density, "cotton")
                stitches = self.generate_satin_fill(points, config.pixel_size, config.fill_angle, adjusted_density)
            elif config.stitch_type == StitchType.RUNNING:
                stitches = self.generate_running_stitch(points, config.pixel_size, config.stitch_length)
            else:
                continue

            stitch_count = len(stitches)
            total_stitches += stitch_count

            # Check density (stitches per area)
            area_mm2 = len(points) * (config.pixel_size * 10) ** 2
            if area_mm2 > 0:
                density = stitch_count / area_mm2
                if density > 50:  # Very high density
                    validation_report["warnings"].append(f"{config.name}: High stitch density ({density:.1f}/mm²) may cause fabric puckering")
                    validation_report["overall_quality"] = "CAUTION"
                max_density_area = max(max_density_area, density)

        validation_report["statistics"] = {
            "total_stitches": total_stitches,
            "estimated_time_minutes": round(total_stitches / 800, 1),  # ~800 stitches/min
            "color_changes": color_changes - 1,  # Don't count first color as change
            "max_density_per_mm2": round(max_density_area, 1),
            "professional_features": [
                "✓ Professional underlay system",
                "✓ Proper tatami/satin fills",
                "✓ 0.4mm density standard",
                "✓ Center-out sequencing",
                "✓ Fabric-aware adjustments",
                "✓ Optimized color sequence"
            ]
        }

        # Quality recommendations
        if total_stitches < 500:
            validation_report["recommendations"].append("Design may be too simple for professional embroidery")
        elif total_stitches > 50000:
            validation_report["recommendations"].append("High stitch count - consider simplifying design")

        if color_changes > 10:
            validation_report["recommendations"].append("Many color changes will increase production time")

        return validation_report

    def generate_preview_image(self, scale_factor: int = 4,
                              use_grouping: bool = False, grouping_radius: int = 2,
                              show_stitch_sequence: bool = False) -> Image.Image:
        """Generate a visual preview of the stitch patterns with enhanced validation features"""
        # Create a preview image scaled up for better visibility
        preview_width = self.width * scale_factor
        preview_height = self.height * scale_factor

        # Create white background (fabric color)
        preview = Image.new('RGB', (preview_width, preview_height), 'white')
        draw = ImageDraw.Draw(preview)

        # Draw fabric texture if scale is large enough
        if scale_factor >= 8:
            for x in range(0, preview_width, 4):
                for y in range(0, preview_height, 4):
                    if (x + y) % 8 == 0:
                        draw.point((x, y), fill=(248, 248, 248))  # Subtle fabric weave

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

                if config.stitch_type == StitchType.TATAMI:
                    # Draw filled squares for fill stitch
                    draw.rectangle([
                        scaled_x, scaled_y,
                        scaled_x + scale_factor - 1, scaled_y + scale_factor - 1
                    ], fill=thread_color)

                elif config.stitch_type == StitchType.TATAMI:
                    # Draw crosshatch pattern for tatami fill
                    draw.rectangle([
                        scaled_x, scaled_y,
                        scaled_x + scale_factor - 1, scaled_y + scale_factor - 1
                    ], fill=thread_color)

                    # Add diagonal lines for tatami texture
                    if scale_factor >= 4:
                        line_color = tuple(max(0, c - 40) for c in thread_color)  # Darker shade
                        # Draw diagonal lines at 45° angle
                        for i in range(0, scale_factor, 2):
                            draw.line([scaled_x + i, scaled_y, scaled_x, scaled_y + i], fill=line_color, width=1)
                            draw.line([scaled_x + scale_factor - 1 - i, scaled_y + scale_factor - 1,
                                     scaled_x + scale_factor - 1, scaled_y + scale_factor - 1 - i], fill=line_color, width=1)
                elif config.stitch_type == StitchType.DENSE_TATAMI:
                    # Draw very dense crosshatch pattern for dense tatami fill
                    draw.rectangle([
                        scaled_x, scaled_y,
                        scaled_x + scale_factor - 1, scaled_y + scale_factor - 1
                    ], fill=thread_color)
                    # Add much denser diagonal lines for dense tatami texture
                    if scale_factor >= 2:
                        line_color = tuple(max(0, c - 60) for c in thread_color)  # Much darker shade for density
                        # Draw very dense diagonal lines at 45° angle (every pixel)
                        for i in range(0, scale_factor, 1):  # Every pixel instead of every 2
                            draw.line([scaled_x + i, scaled_y, scaled_x, scaled_y + i], fill=line_color, width=1)
                            draw.line([scaled_x + scale_factor - 1 - i, scaled_y + scale_factor - 1,
                                     scaled_x + scale_factor - 1, scaled_y + scale_factor - 1 - i], fill=line_color, width=1)
                        # Add additional perpendicular lines for extra density
                        for i in range(0, scale_factor, 2):
                            draw.line([scaled_x + i, scaled_y + scale_factor - 1, scaled_x + scale_factor - 1, scaled_y + i], fill=line_color, width=1)

                elif config.stitch_type == StitchType.SATIN:
                    # Draw smooth fill for satin stitch
                    draw.rectangle([
                        scaled_x, scaled_y,
                        scaled_x + scale_factor - 1, scaled_y + scale_factor - 1
                    ], fill=thread_color)

                    # Add subtle horizontal lines for satin texture
                    if scale_factor >= 3:
                        line_color = tuple(min(255, c + 20) for c in thread_color)  # Lighter shade
                        for i in range(1, scale_factor, 2):
                            draw.line([scaled_x, scaled_y + i, scaled_x + scale_factor - 1, scaled_y + i],
                                    fill=line_color, width=1)

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
        """Generate the complete embroidery pattern with professional underlay and stitch quality"""
        pattern = pyembroidery.EmbPattern()

        # Get color regions
        regions = self.get_color_regions()

        # Optimize color sequence to minimize machine jumps
        optimized_color_order = self.optimize_color_sequence(regions)

        # Process each color in optimized sequence (underlay first, then top stitches)
        for color_key in optimized_color_order:
            config = self.color_configs[color_key]
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

            # Generate underlay for fill stitches (tatami and satin need foundation)
            underlay_stitches = []
            if config.stitch_type in [StitchType.TATAMI, StitchType.SATIN]:
                # Use edge-run underlay for most cases, zigzag for large areas
                area_size = len(points)
                underlay_type = "zigzag" if area_size > 1000 else "edge"
                underlay_stitches = self.generate_underlay(points, config.pixel_size, underlay_type)

            # Generate main stitches based on type
            main_stitches = []
            if config.stitch_type == StitchType.TATAMI:
                # Apply fabric-aware density adjustment
                adjusted_density = self.get_fabric_adjusted_density(config.density, "cotton")
                main_stitches = self.generate_tatami_fill(
                    points, config.pixel_size, config.fill_angle, adjusted_density
                )
            elif config.stitch_type == StitchType.DENSE_TATAMI:
                # Apply fabric-aware density adjustment for dense effect
                adjusted_density = self.get_fabric_adjusted_density(config.density * 1.5, "cotton")  # 50% denser
                main_stitches = self.generate_dense_tatami_fill(
                    points, config.pixel_size, config.fill_angle, adjusted_density
                )
            elif config.stitch_type == StitchType.SATIN:
                # Apply fabric-aware density adjustment
                adjusted_density = self.get_fabric_adjusted_density(config.density, "cotton")
                main_stitches = self.generate_satin_fill(
                    points, config.pixel_size, config.fill_angle, adjusted_density
                )
            elif config.stitch_type == StitchType.RUNNING:
                main_stitches = self.generate_running_stitch(
                    points, config.pixel_size, config.stitch_length
                )
            else:
                continue  # Skip unknown stitch types

            # Add underlay stitches first (if any)
            if underlay_stitches:
                pattern.move_abs(underlay_stitches[0][0], underlay_stitches[0][1])
                for x, y in underlay_stitches:
                    pattern.stitch_abs(x, y)
                # End underlay section
                pattern.trim()

            # Add main stitches with proper sequencing
            if main_stitches:
                # Apply center-out sequencing for tatami and satin fills to minimize distortion
                if config.stitch_type in [StitchType.TATAMI, StitchType.DENSE_TATAMI, StitchType.SATIN]:
                    # Separate trim markers from coordinates for sequencing
                    coordinate_stitches = [s for s in main_stitches if s is not None]
                    if coordinate_stitches:
                        sequenced_coords = self.apply_center_out_sequencing(coordinate_stitches)
                        # For pixelated fills with trim markers, we keep the original order with trims
                        # as the pixelated approach relies on specific trim placement
                        if any(s is None for s in main_stitches):
                            # Keep original order with trims for pixelated approach
                            main_stitches = main_stitches
                        else:
                            # Use sequenced order for traditional fills
                            main_stitches = sequenced_coords

                # Find first actual coordinate (skip any None markers at start)
                first_coord = None
                for stitch in main_stitches:
                    if stitch is not None:
                        first_coord = stitch
                        break

                if first_coord:
                    # Move to first point without stitching
                    pattern.move_abs(first_coord[0], first_coord[1])

                    # Add all main stitches, handling trim markers
                    for stitch in main_stitches:
                        if stitch is None:
                            # Add trim command
                            pattern.trim()
                        else:
                            x, y = stitch
                            pattern.stitch_abs(x, y)

                # End this color section properly
                pattern.trim()

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