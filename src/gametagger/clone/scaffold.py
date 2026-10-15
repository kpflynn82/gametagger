"""Write a runnable web skeleton plus the Codex art handoff from a CloneSpec.

Produces, under ``<out>/<slug>/``:

* ``index.html`` + ``src/main.js`` -- a gray-box that boots (Phaser or three.js from a pinned CDN),
  shows the core loop and screen list, and loads any art Codex has dropped into ``assets/``,
  falling back to coloured placeholders so it runs before a single asset exists.
* ``DIRECTIONS.md`` -- the mechanics brief: what to keep, what to add, the reskin, Kevin's notes.
* ``ART_BRIEF.md`` + ``assets/MANIFEST.json`` -- the Codex handoff: exactly which images to make.
* ``README.md`` -- how to run it, and the Unity-is-the-final-target note.
"""

from __future__ import annotations

import json
from pathlib import Path

from gametagger.clone.spec import CloneSpec

PHASER_CDN = "https://cdnjs.cloudflare.com/ajax/libs/phaser/3.80.1/phaser.min.js"
THREE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.min.js"


def _readme(spec: CloneSpec) -> str:
    return f"""# {spec.title} (prototype)

A fair-by-design clone of a torn-down {spec.family.replace("_", " ")} game, reskinned to
**{spec.theme}**. Mechanics are Claude's; art is Codex's (see `ART_BRIEF.md`).

{spec.source_note}

## Run it

Serve the folder and open it (the scripts load from a CDN):

```
cd {spec.slug}
python3 -m http.server 8080
# open http://localhost:8080
```

The skeleton boots to a gray-box scene that lists the loop and screens and shows placeholder art.
Drop Codex's PNGs into `assets/` (names in `assets/MANIFEST.json`) and reload to see them.

## Engine

Prototype engine: **{spec.engine}** ({spec.dimensionality.upper()}), chosen to iterate fast in a
phone browser. The **final build target is Unity** -- this web prototype proves the loop and feel;
it is not the shipping client.
"""


def _directions_md(spec: CloneSpec) -> str:
    keep = "\n".join(f"- {k}" for k in spec.keep) or "- (fill from the teardown)"
    add = "\n".join(f"- {a}" for a in spec.add) or "- (none)"
    directions = "\n".join(f"- {d}" for d in spec.directions) or "- (none yet)"
    econ = json.dumps(spec.economy, indent=2) if spec.economy else "(to be tuned)"
    return f"""# Directions -- {spec.title}

{spec.source_note}

## Reskin
From its original theme to **{spec.theme}**.

## Core loop
{spec.core_loop}

## Keep (clone faithfully -- the systems that make it work)
{keep}

## Add (new mechanics layered in)
{add}

## Kevin's directions
{directions}

## Screens
{", ".join(spec.screens)}

## Economy
```json
{econ}
```

> Mechanics, economy and progression are copyable; art, characters, names, text and levels are
> not. This clone ships original art (Codex) and original names/strings. (Tetris v. Xio, 2012.)
"""


def _art_brief_md(spec: CloneSpec) -> str:
    rows = "\n".join(f"| `{a.filename}` | {a.size} | {a.description} |" for a in spec.art_assets())
    return f"""# Art brief for Codex -- {spec.title}

**Theme:** {spec.theme}. **Style:** stylized 3D cartoon look (readable on a phone, not too young);
match the polish of a modern top-grosser. **For:** a {spec.family.replace("_", " ")} prototype.

## How this hands off
1. Generate each image below at the given size, transparent background where it is an object.
2. Save it to `assets/` with the exact filename.
3. Commit to the repo. The skeleton loads by these names; no code change needed.

## Assets
| file | size | what it is |
|---|---|---|
{rows}

## Rules
- PNG. Keep a consistent palette and light direction across the set.
- Original art only -- do not copy the torn-down game's art, characters, logo or UI.
- If you add an asset, add it to `assets/MANIFEST.json` too so the loader picks it up.
"""


def _manifest(spec: CloneSpec) -> dict:
    return {
        "title": spec.title,
        "theme": spec.theme,
        "engine": spec.engine,
        "dimensionality": spec.dimensionality,
        "assets": [
            {"name": a.name, "file": a.filename, "size": a.size, "description": a.description}
            for a in spec.art_assets()
        ],
    }


def _index_html(spec: CloneSpec) -> str:
    cdn = PHASER_CDN if spec.engine == "phaser" else THREE_CDN
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>{spec.title} (prototype)</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #10131a; color: #e8ecf4;
    font-family: system-ui, sans-serif; }}
  #game {{ position: fixed; inset: 0; }}
  #overlay {{ position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 12px 14px;
    background: rgba(18,22,32,.78); border: 1px solid #2a3550; border-radius: 12px;
    font-size: 14px; line-height: 1.4; }}
  #overlay b {{ color: #8ab4ff; }}
</style>
</head>
<body>
<div id="game"></div>
<div id="overlay">
  <b>{spec.title}</b> — {spec.theme} · {spec.engine} gray-box<br />
  Loop: {spec.core_loop}
</div>
<script src="{cdn}"></script>
<script type="module" src="src/main.js"></script>
</body>
</html>
"""


def _main_js(spec: CloneSpec) -> str:
    screens = json.dumps(spec.screens)
    keep = json.dumps(spec.keep)
    add = json.dumps(spec.add)
    if spec.engine == "phaser":
        body = f"""// Gray-box: proves the loop boots. Replace scenes as the build grows.
const SCREENS = {screens};
const KEEP = {keep};
const ADD = {add};

async function manifest() {{
  try {{ return await (await fetch('assets/MANIFEST.json')).json(); }}
  catch (e) {{ return {{ assets: [] }}; }}
}}

class Boot extends Phaser.Scene {{
  preload() {{
    this.load.on('loaderror', (f) => console.warn('missing art (placeholder used):', f.key));
  }}
  async create() {{
    const m = await manifest();
    const w = this.scale.width, h = this.scale.height;
    this.add.rectangle(w/2, h/2, w, h, 0x151a24);
    this.add.text(16, 24, '{spec.title}', {{ fontSize: 28, color: '#8ab4ff' }});
    this.add.text(16, 64, 'Screens: ' + SCREENS.join('  ·  '),
      {{ fontSize: 16, color: '#e8ecf4' }});
    this.add.text(16, 96, 'Keep: ' + KEEP.join(', '), {{ fontSize: 14, color: '#b8c2d8' }});
    this.add.text(16, 120, 'Add: ' + ADD.join(', '), {{ fontSize: 14, color: '#7fe0a8' }});
    this.add.text(16, 160, 'Art expected: ' + (m.assets||[]).length + ' files in assets/',
      {{ fontSize: 13, color: '#8893a8' }});
    // A tappable placeholder "play" button proves input works.
    const btn = this.add.rectangle(w/2, h-120, 240, 72, 0x2a63ff).setInteractive();
    this.add.text(w/2, h-120, 'PLAY', {{ fontSize: 22 }}).setOrigin(0.5);
    let runs = 0;
    btn.on('pointerup', () => this.add.text(w/2, h-180, 'run ' + (++runs), {{ fontSize: 16 }})
      .setOrigin(0.5));
  }}
}}

new Phaser.Game({{
  type: Phaser.AUTO, parent: 'game', backgroundColor: '#10131a',
  scale: {{ mode: Phaser.Scale.RESIZE, width: '100%', height: '100%' }},
  scene: [Boot],
}});
"""
    else:
        body = f"""// three.js gray-box: proves the 3D scene boots. Replace with the real loop.
import * as THREE from '{THREE_CDN}';
const SCREENS = {screens};
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x10131a);
const camera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 0.1, 100);
camera.position.set(0, 1.5, 6);
const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setSize(innerWidth, innerHeight);
document.getElementById('game').appendChild(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff, 0x223044, 1.1));
const mesh = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1.5, 1.5),
  new THREE.MeshStandardMaterial({{ color: 0x2a63ff }}));
scene.add(mesh);
addEventListener('resize', () => {{
  camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
}});
(function loop() {{
  requestAnimationFrame(loop); mesh.rotation.y += 0.01; renderer.render(scene, camera);
}})();
console.log('screens:', SCREENS);
"""
    return body


def scaffold_clone(spec: CloneSpec, out_dir: Path) -> dict[str, Path]:
    """Write the skeleton + handoff docs under ``out_dir/<slug>``. Returns {label: path}."""

    root = Path(out_dir) / spec.slug
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    files = {
        "readme": (root / "README.md", _readme(spec)),
        "directions": (root / "DIRECTIONS.md", _directions_md(spec)),
        "art_brief": (root / "ART_BRIEF.md", _art_brief_md(spec)),
        "manifest": (root / "assets" / "MANIFEST.json", json.dumps(_manifest(spec), indent=2)),
        "index": (root / "index.html", _index_html(spec)),
        "main": (root / "src" / "main.js", _main_js(spec)),
    }
    for label, (path, content) in files.items():
        path.write_text(content)
        written[label] = path
    return written
