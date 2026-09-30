"""Join the recorded scenes and the narration into the final video, with crossfades between scenes.

Inputs: work/video/<id>.mp4 (record.mjs) and work/audio/<id>.wav (voice.py).
Output: docs/pitch/video/SurgeSight_TeamEcho_demo.mp4 (1080p, H.264 + AAC).
Run from the repo root:  .venv/bin/python docs/pitch/video/assemble.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
WORK = HERE / "work"
OUT = HERE / "SurgeSight_TeamEcho_demo_v2.mp4"
LEAD = 0.5   # narration starts this long after a scene begins (matches record.mjs)
XF = 0.5     # crossfade length between scenes


def seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def main() -> None:
    scenes = json.loads((HERE / "scenes.json").read_text())["scenes"]
    ids = [s["id"] for s in scenes]
    kinds = {s["id"]: s["kind"] for s in scenes}
    lens = [seconds(WORK / "video" / f"{i}.mp4") for i in ids]
    args = ["ffmpeg", "-y", "-v", "error"]
    for i in ids:
        args += ["-i", str(WORK / "video" / f"{i}.mp4")]
    for i in ids:
        args += ["-i", str(WORK / "audio" / f"{i}.wav")]
    n, parts = len(ids), []
    ms = int(LEAD * 1000)
    for k in range(n):
        parts.append(f"[{k}:v]settb=AVTB,setpts=PTS-STARTPTS,fps=30[v{k}]")
        parts.append(f"[{n + k}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},apad,atrim=0:{lens[k]:.3f}[a{k}]")
    v, a, offset = "v0", "a0", 0.0
    for k in range(1, n):
        offset += lens[k - 1] - XF
        # Slide between two app screens, fade in and out of the motion cards.
        trans = "smoothleft" if kinds[ids[k]] == kinds[ids[k - 1]] == "app" else "fade"
        parts.append(f"[{v}][v{k}]xfade=transition={trans}:duration={XF}:offset={offset:.3f}[vx{k}]")
        parts.append(f"[{a}][a{k}]acrossfade=d={XF}:c1=tri:c2=tri[ax{k}]")
        v, a = f"vx{k}", f"ax{k}"
    total = sum(lens) - XF * (n - 1)
    parts.append(f"[{v}]fade=t=in:st=0:d=0.6,fade=t=out:st={total - 0.8:.3f}:d=0.8,format=yuv420p[vout]")
    parts.append(f"[{a}]afade=t=out:st={total - 0.8:.3f}:d=0.8,loudnorm=I=-16:TP=-1.5[aout]")
    args += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(OUT)]
    subprocess.run(args, check=True)
    print(f"{OUT}  {seconds(OUT):.1f}s  {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
