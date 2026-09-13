"""
ManimGL Render Backend
Render.com pe deploy karne ke liye.
"""

import os, re, uuid, shutil, subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

CONFIG_YML = BASE_DIR / "manim_config.yml"
CONFIG_YML.write_text("""
directories:
  mirror_module_path: False
  output: "./outputs"
  cache: "./cache"
camera:
  resolution: (1280, 720)
  background_color: "#000000"
  fps: 30
file_writer:
  video_codec: "libx264"
  pixel_format: "yuv420p"
  crf: 23
  preset: "medium"
""", encoding="utf-8")

QUALITY_FLAGS = {"low":"-l", "medium":"-m", "high":"-hd", "4k":"-uhd"}

FORBIDDEN = [
    r"\bimport\s+os\b", r"\bimport\s+sys\b", r"\bimport\s+subprocess\b",
    r"\bimport\s+socket\b", r"\bimport\s+shutil\b", r"\bimport\s+pathlib\b",
    r"\b__import__\s*\(", r"\beval\s*\(", r"\bexec\s*\(",
    r"\bopen\s*\(", r"\bcompile\s*\(", r"from\s+os\b", r"from\s+sys\b",
]

def is_code_safe(code):
    for p in FORBIDDEN:
        if re.search(p, code): return False, f"Blocked: {p}"
    if len(code) > 100_000: return False, "Code too long"
    return True, ""

def extract_scene_name(code):
    m = re.search(r"class\s+(\w+)\s*\(\s*(?:\w+\.)?(?:Scene|ThreeDScene|InteractiveScene)\s*\)", code)
    return m.group(1) if m else None

def render_scene(code, scene_name, quality):
    safe, msg = is_code_safe(code)
    if not safe: return {"success": False, "error": msg}
    if not scene_name:
        scene_name = extract_scene_name(code)
        if not scene_name:
            return {"success": False, "error": "No Scene class found. Example: class MyScene(Scene): ..."}

    job_id = uuid.uuid4().hex[:12]
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "video").mkdir(exist_ok=True)
    (job_dir / "scene.py").write_text(code, encoding="utf-8")

    cmd = ["manimgl", str(job_dir / "scene.py"), scene_name, "-w",
           QUALITY_FLAGS.get(quality, "-m"),
           "--config_file", str(CONFIG_YML),
           "--video_dir", str(job_dir / "video")]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=600, cwd=str(job_dir),
                                env={**os.environ, "PYTHONUNBUFFERED":"1"})
        if result.returncode != 0:
            return {"success": False, "error": (result.stderr or result.stdout or "Unknown")[-3000:]}

        candidates = list((job_dir/"video").rglob(f"{scene_name}*.mp4")) + list(job_dir.rglob("*.mp4"))
        if not candidates:
            return {"success": False, "error": "No MP4 found.\n" + result.stdout[-800:]}

        final = job_dir / f"{scene_name}.mp4"
        shutil.copy2(candidates[0], final)
        return {"success": True, "job_id": job_id, "scene_name": scene_name,
                "video_url": f"/outputs/{job_id}/{final.name}", "log": (result.stdout or "")[-1500:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout (10 min)"}
    except FileNotFoundError:
        return {"success": False, "error": "manimgl not found"}
    except Exception as e:
        return {"success": False, "error": f"Server error: {e}"}

app = FastAPI(title="ManimGL Render API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

class RenderRequest(BaseModel):
    code: str = Field(..., min_length=5, max_length=100_000)
    scene_name: str | None = None
    quality: str = "medium"

@app.get("/api/health")
def health():
    try:
        r = subprocess.run(["manimgl","--version"], capture_output=True, text=True, timeout=5)
        v = (r.stdout or r.stderr or "").strip().splitlines()[0] if (r.stdout or r.stderr) else "unknown"
        return {"manimgl_installed": True, "version": v}
    except Exception:
        return {"manimgl_installed": False, "version": None}

@app.post("/api/render")
def render(req: RenderRequest):
    result = render_scene(req.code, req.scene_name, req.quality)
    if not result["success"]:
        raise HTTPException(500, result["error"])
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
