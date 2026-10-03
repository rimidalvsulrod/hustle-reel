#!/usr/bin/env python3
"""Build the NEQO Digital Ultra ($999/mo) light-theme Instagram reel.

Reuses the shared reel pipeline (../reel/make_reel.py: Gemini TTS, VO-synced timeline, Chromium frame render,
music/SFX mix, ffmpeg export) with this folder's script and scene.html.

Usage:  GEMINI_API_KEY=... python3 neqo999/make_reel.py [--regen]
"""
import importlib.util, os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("reel_pipeline", os.path.join(HERE, "..", "reel", "make_reel.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

base.HERE, base.BUILD, base.OUT = HERE, os.path.join(HERE, "build"), os.path.join(HERE, "neqo-ultra-999-reel.mp4")
# One spoken line per scene in scene.html (matched by id). "Neeko" is the phonetic spelling of NEQO (NEE-koh).
base.LINES = []  # filled in from the chosen concept
base.PROMPT = ""

if __name__ == "__main__":
    base.main()
