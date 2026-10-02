#!/usr/bin/env python3
"""Build the Stay Minted fresh-pressed juice Instagram reel.

Reuses the NEQO reel pipeline (../reel/make_reel.py: Gemini TTS, VO-synced timeline, Chromium frame render,
music/SFX mix, ffmpeg export) with this folder's script, scene.html, brand assets pulled from the live site
and a brighter 118 BPM major-key bed.

Usage:  GEMINI_API_KEY=... python3 stayminted/make_reel.py [--regen]
"""
import importlib.util, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("reel_pipeline", os.path.join(HERE, "..", "reel", "make_reel.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

SITE = "https://stay-minted.vercel.app"
base.HERE, base.BUILD, base.OUT = HERE, os.path.join(HERE, "build"), os.path.join(HERE, "stay-minted-reel.mp4")
# One spoken line per scene in scene.html (matched by id).
base.LINES = [
    ("hook", "Still drinking juice from concentrate?"),
    ("meet", "Meet Stay Minted."),
    ("fresh", "Fresh-pressed juice from New Britain, Connecticut."),
    ("pine", "Pineapple Mint: tropical and crisp."),
    ("ginger", "Ginger, with a kick."),
    ("orange", "Oranges: pure sunshine."),
    ("turmeric", "Turmeric: liquid gold."),
    ("real", "Real fruit, real roots. Nothing you can't pronounce."),
    ("end", "Stay Minted. Fresh. Pressed. Juices. Follow at Stay Minted."),
]
base.PROMPT = """# AUDIO PROFILE: Hype announcer for a 20-second Instagram ad for a fresh-pressed juice brand
### DIRECTOR'S NOTES
Style: bright, high-energy, upbeat and fun, with a big smile in the voice; punchy emphasis on the flavor names.
Pace: fast, rapid-fire delivery with only a short beat between lines.
### TRANSCRIPT
"""
base.BPM, base.STAB = 118, "pluck"
base.PROG = [(43.65, (174.61, 220.0, 261.63)), (65.41, (164.81, 196.0, 261.63)),  # F  C
             (73.42, (174.61, 220.0, 293.66)), (58.27, (174.61, 233.08, 293.66))]  # Dm Bb
inter_fonts = base.fetch_fonts


def fetch_assets():
    """Inter (Google Fonts) plus the brand's own fonts and bottle cutout from the live site."""
    inter_fonts()
    for rel in ("fonts/anton.woff2", "fonts/yellowtail.woff2", "fonts/kalam.woff2", "bottle.webp"):
        path = os.path.join(base.BUILD, rel)
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            req = urllib.request.Request(f"{SITE}/{rel}", headers={"User-Agent": "Mozilla/5.0"})
            open(path, "wb").write(urllib.request.urlopen(req, timeout=60).read())


base.fetch_fonts = fetch_assets

if __name__ == "__main__":
    base.main()
