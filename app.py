#!/usr/bin/env python3
"""
MVP Embroidery Converter - Simple version that actually works
Based on the working simple_app.py but with better colors and minimal UI
"""

from flask import Flask, render_template_string, jsonify, request
import base64
import io
import json
from embroidery_converter import EmbroideryConverter, StitchType

app = Flask(__name__)
converter = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Embroidery Converter MVP</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 100vw; margin: 0; padding: 10px; font-size: 14px; height: 100vh; box-sizing: border-box; }
        h1 { margin: 0 0 15px 0; font-size: 1.5em; text-align: center; }
        .main-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; height: calc(100vh - 60px); }
        .panel { background: #f8f9fa; border-radius: 8px; padding: 12px; overflow-y: auto; }

        /* Controls Panel */
        .controls-panel h2 { margin: 0 0 10px 0; font-size: 1.1em; }
        .control-group { margin: 8px 0; padding: 8px; background: white; border-radius: 4px; border: 1px solid #dee2e6; }
        .control-row { display: flex; align-items: center; margin: 3px 0; }
        .control-label { min-width: 80px; font-size: 12px; font-weight: bold; }
        input[type="range"] { flex: 1; margin: 0 8px; }
        input[type="number"] { width: 50px; padding: 2px; font-size: 12px; }
        select, button { padding: 6px 8px; font-size: 12px; margin: 2px; }
        button { background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .size-info { font-size: 11px; color: #666; margin-top: 3px; }

        /* Colors Panel */
        .color-card { border: 1px solid #ddd; padding: 8px; margin: 5px 0; border-radius: 4px; background: white; }
        .color-swatch { width: 20px; height: 20px; display: inline-block; margin-right: 8px; border: 1px solid #000; vertical-align: middle; }
        .color-name { font-weight: bold; font-size: 12px; }
        .color-info { font-size: 11px; color: #666; margin: 2px 0; }

        /* Stats and Preview Panel */
        .stats-preview-panel { display: flex; flex-direction: column; }
        .stats-section { background: white; padding: 8px; margin: 5px 0; border-radius: 4px; border: 1px solid #dee2e6; }
        .stats-section h3 { margin: 0 0 5px 0; font-size: 0.9em; }
        .stats-mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
        .stat-item { padding: 6px; background: #f8f9fa; border-radius: 3px; text-align: center; }
        .stat-label { font-size: 10px; font-weight: bold; color: #495057; }
        .stat-value { font-size: 14px; color: #007bff; font-weight: bold; }

        .preview-container { flex: 1; display: flex; align-items: center; justify-content: center; background: white; border-radius: 4px; border: 1px solid #dee2e6; min-height: 200px; }
        #preview-image { max-width: 100%; max-height: 100%; object-fit: contain; }

        .status { padding: 6px; margin: 5px 0; border-radius: 4px; font-size: 12px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>🧵 Embroidery Converter MVP</h1>

    <div class="main-grid">
        <!-- Controls Panel -->
        <div class="panel controls-panel">
            <h2>🎛️ Controls</h2>

            <div class="control-group">
                <div class="control-row">
                    <span class="control-label">Scale:</span>
                    <input type="range" id="scaleSlider" min="0.25" max="3.0" step="0.25" value="1.0"
                           onchange="updateScaleDisplay()">
                    <input type="number" id="scaleValue" min="0.25" max="3.0" step="0.25" value="1.0"
                           onchange="updateScaleSlider()">
                </div>
                <div class="size-info" id="scaledSizeInfo">675×450 pixels</div>
            </div>

            <button onclick="loadImage()">📂 Load Image</button>
            <div id="status"></div>

            <button onclick="exportDST()" style="width: 100%; margin-top: 10px;">💾 Export DST</button>
        </div>

        <!-- Colors Panel -->
        <div class="panel">
            <h2>🎨 Colors</h2>
            <div id="colors">
                <p style="text-align: center; color: #666; font-size: 12px;">Load image to see colors</p>
            </div>
        </div>

        <!-- Stats & Preview Panel -->
        <div class="panel stats-preview-panel">
            <div id="statistics"></div>

            <h2>🖼️ Preview</h2>
            <div class="preview-container" id="preview-container">
                <p style="color: #666; font-size: 12px;">Preview will appear here</p>
            </div>
        </div>
    </div>

    <script>
        let currentColors = {};

        async function loadImage() {
            try {
                const response = await fetch('/load');
                const data = await response.json();

                if (data.success) {
                    document.getElementById('status').innerHTML = '<div class="status success">✅ Image loaded successfully!</div>';
                    currentColors = data.colors;
                    displayColors(data.colors);
                } else {
                    document.getElementById('status').innerHTML = `<div class="status error">❌ Error: ${data.error}</div>`;
                }
            } catch (error) {
                document.getElementById('status').innerHTML = `<div class="status error">❌ Error: ${error.message}</div>`;
            }
        }

        function displayColors(colors) {
            let html = '';
            for (const [key, color] of Object.entries(colors)) {
                const rgb = `rgb(${color.rgb[0]}, ${color.rgb[1]}, ${color.rgb[2]})`;
                html += `
                    <div class="color-card">
                        <div style="display: flex; align-items: center; margin-bottom: 6px;">
                            <div class="color-swatch" style="background-color: ${rgb}"></div>
                            <div class="color-name">${color.name}</div>
                        </div>
                        <div class="color-info">${color.pixel_count.toLocaleString()} pixels</div>

                        <select style="width: 100%; margin: 4px 0;" onchange="updateStitch('${key}', this.value, null)">
                            <option value="none" ${color.stitch_type === 'none' ? 'selected' : ''}>None</option>
                            <option value="fill" ${color.stitch_type === 'fill' ? 'selected' : ''}>Fill</option>
                            <option value="cross" ${color.stitch_type === 'cross' ? 'selected' : ''}>Cross</option>
                            <option value="running" ${color.stitch_type === 'running' ? 'selected' : ''}>Running</option>
                        </select>

                        <div class="control-row">
                            <span class="control-label">Size:</span>
                            <input type="range" id="pixelSlider_${key}" min="0.5" max="10.0" step="0.5" value="${color.pixel_size}"
                                   oninput="syncPixelControls('${key}', this.value); updateStitch('${key}', null, this.value)">
                            <input type="number" id="pixelNumber_${key}" min="0.5" max="10.0" step="0.5" value="${color.pixel_size}"
                                   oninput="syncPixelControls('${key}', this.value); updateStitch('${key}', null, this.value)">
                        </div>
                    </div>
                `;
            }
            document.getElementById('colors').innerHTML = html;
        }

        function updateStitch(colorKey, stitchType, pixelSize) {
            if (currentColors[colorKey]) {
                if (stitchType !== null) {
                    currentColors[colorKey].stitch_type = stitchType;
                }
                if (pixelSize !== null) {
                    currentColors[colorKey].pixel_size = parseFloat(pixelSize);
                }
                // Automatically refresh statistics and preview
                refreshStatisticsAndPreview();
            }
        }

        function updateScaleDisplay() {
            const scale = parseFloat(document.getElementById('scaleSlider').value);
            document.getElementById('scaleValue').value = scale;
            updateScaledSizeInfo(scale);
            debouncedLoadImage();
        }

        function updateScaleSlider() {
            const scale = parseFloat(document.getElementById('scaleValue').value);
            document.getElementById('scaleSlider').value = scale;
            updateScaledSizeInfo(scale);
            debouncedLoadImage();
        }

        function updateScaledSizeInfo(scale) {
            const originalWidth = 675;
            const originalHeight = 450;
            const newWidth = Math.round(originalWidth * scale);
            const newHeight = Math.round(originalHeight * scale);
            document.getElementById('scaledSizeInfo').textContent =
                `Scaled size will be ${newWidth}×${newHeight} pixels (${scale}x scale)`;
        }

        async function loadImage() {
            try {
                const scale = parseFloat(document.getElementById('scaleValue').value);
                const response = await fetch(`/load?scale=${scale}`);
                const data = await response.json();

                if (data.success) {
                    document.getElementById('status').innerHTML = '<div class="status success">✅ Image loaded successfully!</div>';
                    currentColors = data.colors;
                    displayColors(data.colors);

                    // Update the size info with actual loaded size
                    const actualSize = data.image_size;
                    document.getElementById('scaledSizeInfo').textContent =
                        `Loaded size: ${actualSize} (${data.scale_factor}x scale)`;

                    // Automatically show statistics and preview
                    await refreshStatisticsAndPreview();
                } else {
                    document.getElementById('status').innerHTML = `<div class="status error">❌ Error: ${data.error}</div>`;
                }
            } catch (error) {
                document.getElementById('status').innerHTML = `<div class="status error">❌ Error: ${error.message}</div>`;
            }
        }

        // Debounce functions to prevent too many rapid updates
        let refreshTimeout;
        function refreshStatisticsAndPreview() {
            clearTimeout(refreshTimeout);
            refreshTimeout = setTimeout(async () => {
                await showStatistics();
                await generatePreview();
            }, 300); // Wait 300ms after last change
        }

        let scaleTimeout;
        function debouncedLoadImage() {
            clearTimeout(scaleTimeout);
            scaleTimeout = setTimeout(() => {
                if (currentColors && Object.keys(currentColors).length > 0) {
                    loadImage();
                }
            }, 500); // Wait 500ms after last scale change
        }

        function syncPixelControls(colorKey, value) {
            const slider = document.getElementById(`pixelSlider_${colorKey}`);
            const number = document.getElementById(`pixelNumber_${colorKey}`);
            if (slider) slider.value = value;
            if (number) number.value = value;
        }

        async function showStatistics() {
            try {
                // Update the stitch types first
                if (currentColors && Object.keys(currentColors).length > 0) {
                    await fetch('/update_stitches', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(currentColors)
                    });
                }

                // Get statistics
                const response = await fetch('/statistics');
                const data = await response.json();

                if (data.success) {
                    displayStatistics(data);
                } else {
                    document.getElementById('statistics').innerHTML = `<div class="status error">❌ Error: ${data.error}</div>`;
                }
            } catch (error) {
                document.getElementById('statistics').innerHTML = `<div class="status error">❌ Error: ${error.message}</div>`;
            }
        }

        function displayStatistics(data) {
            const { image_stats, color_stats, embroidery_stats } = data;

            let html = `
                <div class="stats-section">
                    <h3>📊 Quick Stats</h3>
                    <div class="stats-mini-grid">
                        <div class="stat-item">
                            <div class="stat-label">Size</div>
                            <div class="stat-value">${image_stats.width}×${image_stats.height}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">Stitches</div>
                            <div class="stat-value">${Math.round(embroidery_stats.total_expected_stitches/1000)}k</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">Time</div>
                            <div class="stat-value">${embroidery_stats.estimated_hours}h</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">Thread</div>
                            <div class="stat-value">${embroidery_stats.thread_usage_meters}m</div>
                        </div>
                    </div>
                </div>
            `;

            document.getElementById('statistics').innerHTML = html;
        }

        async function generatePreview() {
            try {
                // Update the stitch types first
                await fetch('/update_stitches', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(currentColors)
                });

                // Generate preview
                const response = await fetch('/preview');
                const data = await response.json();

                if (data.success) {
                    document.getElementById('preview-container').innerHTML =
                        `<div style="display: flex; flex-direction: column; align-items: center; height: 100%;">
                            <img id="preview-image" src="${data.preview_image}" alt="Embroidery Preview" style="flex: 1; object-fit: contain;">
                            <p style="margin: 5px 0 0 0; font-size: 11px; color: #666;">Size: ${data.size}</p>
                         </div>`;
                } else {
                    document.getElementById('preview-container').innerHTML = `<p class="error">❌ Error: ${data.error}</p>`;
                }
            } catch (error) {
                document.getElementById('preview-container').innerHTML = `<p class="error">❌ Error: ${error.message}</p>`;
            }
        }

        async function exportDST() {
            try {
                const response = await fetch('/export', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({filename: 'embroidery_output.dst'})
                });
                const data = await response.json();

                if (data.success) {
                    alert(`✅ DST file exported: ${data.filename}`);
                } else {
                    alert(`❌ Export failed: ${data.error}`);
                }
            } catch (error) {
                alert(`❌ Export error: ${error.message}`);
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/load')
def load_image():
    """Load image and set up good defaults - based on working simple_app.py"""
    global converter

    try:
        # Get optional scale parameter
        scale = request.args.get('scale', type=float, default=1.0)

        converter = EmbroideryConverter('leftys_horses_tag_bg.png')

        # Scale the image if requested
        if scale != 1.0:
            from PIL import Image
            original_image = converter.image
            new_width = int(converter.width * scale)
            new_height = int(converter.height * scale)
            scaled_image = original_image.resize((new_width, new_height), Image.NEAREST)

            # Update converter with scaled image
            converter.image = scaled_image
            converter.width, converter.height = scaled_image.size
            converter.pixels = __import__('numpy').array(scaled_image)
            converter._analyze_colors()

        # Set good defaults like simple_app.py did
        converter.update_color_config('color_2', StitchType.CROSS, 2.0)  # Blue -> cross stitch
        converter.update_color_config('color_3', StitchType.CROSS, 2.0)  # Green -> cross stitch

        # Get the configuration
        config = json.loads(converter.get_config_json())
        regions = converter.get_color_regions()

        # Add pixel counts
        for color_key in config:
            config[color_key]['pixel_count'] = len(regions[color_key])

        return jsonify({
            'success': True,
            'colors': config,
            'image_size': f"{converter.width}x{converter.height}",
            'scale_factor': scale
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_stitches', methods=['POST'])
def update_stitches():
    """Update stitch types and pixel sizes based on user selection"""
    global converter

    if not converter:
        return jsonify({'success': False, 'error': 'No image loaded'})

    try:
        colors = request.json
        for color_key, color_data in colors.items():
            if color_key in converter.color_configs:
                stitch_type = StitchType(color_data['stitch_type'])
                pixel_size = color_data.get('pixel_size', 2.0)
                converter.update_color_config(color_key, stitch_type, pixel_size)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/preview')
def generate_preview():
    """Generate preview with bright visible colors - based on working simple_app.py"""
    global converter

    if not converter:
        return jsonify({'success': False, 'error': 'No image loaded'})

    try:
        # Save original colors
        original_colors = {}
        for key, config in converter.color_configs.items():
            original_colors[key] = config.rgb

        # Use bright visible colors for preview
        converter.color_configs['color_1'].rgb = (0, 0, 0)        # Black
        converter.color_configs['color_2'].rgb = (100, 80, 255)   # Bright blue
        converter.color_configs['color_3'].rgb = (60, 200, 120)   # Bright green
        converter.color_configs['color_4'].rgb = (120, 120, 120)  # Light gray

        # Generate preview exactly like simple_app.py
        preview_img = converter.generate_preview_image(scale_factor=4)

        # Restore original colors
        for key, color in original_colors.items():
            converter.color_configs[key].rgb = color

        # Convert to base64
        img_buffer = io.BytesIO()
        preview_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        img_data_url = f"data:image/png;base64,{img_base64}"

        return jsonify({
            'success': True,
            'preview_image': img_data_url,
            'size': f"{preview_img.size[0]}x{preview_img.size[1]}"
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/statistics')
def get_statistics():
    """Get detailed statistics about the embroidery pattern"""
    global converter

    if not converter:
        return jsonify({'success': False, 'error': 'No image loaded'})

    try:
        # Get color regions
        regions = converter.get_color_regions()

        # Calculate statistics
        total_pixels = converter.width * converter.height
        used_pixels = sum(len(points) for points in regions.values())

        color_stats = []
        total_expected_stitches = 0

        for color_key, config in converter.color_configs.items():
            points = regions[color_key]
            count = len(points)
            percentage = (count / used_pixels) * 100 if used_pixels > 0 else 0

            # Calculate expected stitches
            if config.stitch_type == StitchType.NONE:
                expected_stitches = 0
            elif config.stitch_type == StitchType.FILL:
                expected_stitches = count
            elif config.stitch_type == StitchType.CROSS:
                expected_stitches = count * 4  # Each cross = 4 stitches
            else:
                expected_stitches = count

            total_expected_stitches += expected_stitches

            color_stats.append({
                'name': config.name,
                'rgb': config.rgb,
                'stitch_type': config.stitch_type.value,
                'pixel_count': count,
                'percentage': round(percentage, 1),
                'pixel_size': config.pixel_size,
                'expected_stitches': expected_stitches
            })

        # Calculate estimates
        estimated_minutes = total_expected_stitches / 800  # 800 stitches per minute
        estimated_hours = estimated_minutes / 60
        thread_usage_meters = (total_expected_stitches * 2) / 1000  # 2mm per stitch

        return jsonify({
            'success': True,
            'image_stats': {
                'width': converter.width,
                'height': converter.height,
                'total_pixels': total_pixels,
                'used_pixels': used_pixels
            },
            'color_stats': color_stats,
            'embroidery_stats': {
                'total_expected_stitches': total_expected_stitches,
                'estimated_minutes': round(estimated_minutes, 1),
                'estimated_hours': round(estimated_hours, 1),
                'thread_usage_meters': round(thread_usage_meters, 1)
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/export', methods=['POST'])
def export_dst():
    """Export DST file"""
    global converter

    if not converter:
        return jsonify({'success': False, 'error': 'No image loaded'})

    try:
        filename = request.json.get('filename', 'embroidery_output.dst')
        converter.export_dst(filename)

        return jsonify({
            'success': True,
            'filename': filename
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5003)