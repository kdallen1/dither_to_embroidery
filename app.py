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
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
        .container { display: flex; gap: 20px; }
        .controls { flex: 1; }
        .preview { flex: 1; }
        .color-card { border: 1px solid #ccc; padding: 15px; margin: 10px 0; border-radius: 8px; }
        .color-swatch { width: 30px; height: 30px; display: inline-block; margin-right: 10px; border: 1px solid #000; }
        select, button { padding: 8px; margin: 5px; }
        button { background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        #preview-image { max-width: 100%; border: 2px solid #007bff; }
        .status { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>🧵 Embroidery Converter MVP</h1>

    <div class="container">
        <div class="controls">
            <h2>1. Load Image</h2>
            <button onclick="loadImage()">Load leftys_horses_tag_bg.png</button>
            <div id="status"></div>

            <div id="colors"></div>

            <h2>2. Generate Preview</h2>
            <button onclick="generatePreview()">Generate Preview</button>

            <h2>3. Export DST</h2>
            <button onclick="exportDST()">Export DST File</button>
        </div>

        <div class="preview">
            <h2>Preview</h2>
            <div id="preview-container">
                <p>Load image and generate preview to see embroidery pattern</p>
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
            let html = '<h2>Detected Colors</h2>';
            for (const [key, color] of Object.entries(colors)) {
                const rgb = `rgb(${color.rgb[0]}, ${color.rgb[1]}, ${color.rgb[2]})`;
                html += `
                    <div class="color-card">
                        <div class="color-swatch" style="background-color: ${rgb}"></div>
                        <strong>${color.name}</strong> (${color.pixel_count} pixels)
                        <br>
                        Stitch Type:
                        <select onchange="updateStitch('${key}', this.value)">
                            <option value="none" ${color.stitch_type === 'none' ? 'selected' : ''}>None (Fabric)</option>
                            <option value="fill" ${color.stitch_type === 'fill' ? 'selected' : ''}>Fill</option>
                            <option value="cross" ${color.stitch_type === 'cross' ? 'selected' : ''}>Cross Stitch</option>
                            <option value="running" ${color.stitch_type === 'running' ? 'selected' : ''}>Running</option>
                        </select>
                    </div>
                `;
            }
            document.getElementById('colors').innerHTML = html;
        }

        function updateStitch(colorKey, stitchType) {
            if (currentColors[colorKey]) {
                currentColors[colorKey].stitch_type = stitchType;
            }
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
                        `<img id="preview-image" src="${data.preview_image}" alt="Embroidery Preview">
                         <p>Size: ${data.size}</p>`;
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
        converter = EmbroideryConverter('leftys_horses_tag_bg.png')

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
            'image_size': f"{converter.width}x{converter.height}"
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_stitches', methods=['POST'])
def update_stitches():
    """Update stitch types based on user selection"""
    global converter

    if not converter:
        return jsonify({'success': False, 'error': 'No image loaded'})

    try:
        colors = request.json
        for color_key, color_data in colors.items():
            if color_key in converter.color_configs:
                stitch_type = StitchType(color_data['stitch_type'])
                converter.update_color_config(color_key, stitch_type, 2.0)

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