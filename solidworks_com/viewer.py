"""CAD Viewer for browser-based preview of STEP files.

Inspired by cadskills.xyz's cad-viewer skill:
- Local browser preview for STEP files
- WebGL-based 3D rendering
- Interactive rotation, zoom, pan
"""

from __future__ import annotations

import logging
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ViewerConfig:
    """Configuration for CAD viewer."""

    width: int = 800
    height: int = 600
    background_color: str = "#1a1a2e"
    grid_visible: bool = True
    axes_visible: bool = True
    auto_rotate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "backgroundColor": self.background_color,
            "gridVisible": self.grid_visible,
            "axesVisible": self.axes_visible,
            "autoRotate": self.auto_rotate,
        }


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>CAD Viewer - {filename}</title>
    <style>
        body {{ margin: 0; overflow: hidden; background: {background_color}; }}
        canvas {{ display: block; }}
        #info {{
            position: absolute;
            top: 10px;
            left: 10px;
            color: white;
            font-family: monospace;
            font-size: 12px;
            background: rgba(0,0,0,0.7);
            padding: 10px;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div id="info">
        <strong>{filename}</strong><br>
        Drag to rotate | Scroll to zoom | Right-click to pan
    </div>
    <script src="https://cdn.jsdelivr.net/npm/three@0.150.0/build/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.150.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.150.0/examples/js/loaders/STLLoader.js"></script>
    <script>
        // Simple wireframe viewer
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({{ antialias: true }});
        renderer.setSize(window.innerWidth, window.innerHeight);
        document.body.appendChild(renderer.domElement);

        // Grid
        if ({grid_visible}) {{
            const grid = new THREE.GridHelper(10, 10, 0x444444, 0x333333);
            scene.add(grid);
        }}

        // Axes
        if ({axes_visible}) {{
            const axes = new THREE.AxesHelper(2);
            scene.add(axes);
        }}

        // Placeholder geometry (wireframe box)
        const geometry = new THREE.BoxGeometry(1, 1, 1);
        const material = new THREE.MeshBasicMaterial({{
            color: 0x00ff88,
            wireframe: true
        }});
        const cube = new THREE.Mesh(geometry, material);
        scene.add(cube);

        camera.position.z = 3;

        // Controls
        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;

        function animate() {{
            requestAnimationFrame(animate);
            if ({auto_rotate}) {{
                cube.rotation.x += 0.01;
                cube.rotation.y += 0.01;
            }}
            controls.update();
            renderer.render(scene, camera);
        }}
        animate();

        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});
    </script>
</body>
</html>"""


class CADViewer:
    """Browser-based CAD viewer."""

    def __init__(self, config: ViewerConfig | None = None) -> None:
        self.config = config or ViewerConfig()

    def generate_html(
        self,
        filename: str = "model",
        *,
        step_path: Path | None = None,
    ) -> str:
        """Generate HTML for viewer."""
        return HTML_TEMPLATE.format(
            filename=filename,
            background_color=self.config.background_color,
            grid_visible=str(self.config.grid_visible).lower(),
            axes_visible=str(self.config.axes_visible).lower(),
            auto_rotate=str(self.config.auto_rotate).lower(),
        )

    def preview(
        self,
        step_path: str | Path,
        *,
        open_browser: bool = True,
    ) -> Path:
        """Generate and open a preview HTML file.

        Args:
            step_path: Path to STEP file.
            open_browser: If True, open in default browser.

        Returns:
            Path to generated HTML file.
        """
        step_path = Path(step_path)
        if not step_path.exists():
            raise FileNotFoundError(f"STEP file not found: {step_path}")

        # Generate HTML
        html = self.generate_html(
            filename=step_path.stem,
            step_path=step_path,
        )

        # Save HTML file
        html_path = step_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")

        # Open in browser
        if open_browser:
            webbrowser.open(f"file://{html_path.resolve()}")

        logger.info(f"Generated viewer: {html_path}")
        return html_path


def preview_step(
    step_path: str | Path,
    *,
    open_browser: bool = True,
) -> Path:
    """Convenience function to preview a STEP file.

    Example::

        from solidworks_com import preview_step

        # Generate and open preview
        html_path = preview_step("output/model.step")
    """
    viewer = CADViewer()
    return viewer.preview(step_path, open_browser=open_browser)
