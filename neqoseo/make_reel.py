#!/usr/bin/env python3
"""Build the NEQO Digital "Local SEO - rank #1 on Google" Instagram reel (dark nebula style).

Reuses the shared reel pipeline (../reel/make_reel.py: Gemini TTS, VO-synced timeline, Chromium frame render,
music/SFX mix, ffmpeg export) with this folder's script and scene.html.

Usage:  GEMINI_API_KEY=... python3 neqoseo/make_reel.py [--regen]
"""
import importlib.util, os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("reel_pipeline", os.path.join(HERE, "..", "reel", "make_reel.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

base.HERE, base.BUILD, base.OUT = HERE, os.path.join(HERE, "build"), os.path.join(HERE, "neqo-local-seo-reel.mp4")
# One spoken line per scene in scene.html (matched by id). "Neeko" is the phonetic spelling of NEQO (NEE-koh).
base.LINES = [
    ("hook", "Want to rank number one on Google?"),
    ("search", "Your customers are searching."),
    ("buried", "Not on top? They call someone else."),
    ("meet", "Neeko Digital fixes that, with local SEO."),
    ("profile", "Your Google Business Profile, set up right."),
    ("site", "A website built to rank."),
    ("reviews", "Review requests on autopilot."),
    ("climb", "Monthly local SEO pushes you up the map."),
    ("first", "Be the first they call."),
    ("end", "Neeko Digital. Plans from two hundred ninety-nine dollars a month. No contracts."),
]
base.PROMPT = """# AUDIO PROFILE: Hype announcer for a 25-second Instagram ad for a local marketing agency
### DIRECTOR'S NOTES
Style: confident, high-energy, upbeat male announcer with a smile in the voice; crisp diction; punchy emphasis on the key words ("number one", "someone else", "up the map", "first").
Pace: fast and energetic. Read every line of the transcript as its own sentence and leave a clear, short pause (about half a second) after each line; never run two lines together.
Numbers: say "number one" exactly as written. Say the price in full exactly as written, including the words "hundred" and "dollars": "two hundred ninety-nine dollars".
Pronunciation: "Neeko" is pronounced NEE-koh. "SEO" is spelled out: S-E-O.
### TRANSCRIPT
"""

# Dark 124 BPM tech-house (shared defaults: saw stabs over Am - F - C - G), gentle ducking under the voice.
base.CRF, base.MUSIC_GAIN = 17, 0.45
base.SFX_GAIN = {"drop": .5, "sweep": .5, "shimmer": .6, "impact": .7, "thump": .8, "glitch": .8}
base.DUCK = dict(threshold=.06, ratio=2, attack=15, release=900)  # shallow + slow: no pumping between lines
base.SFX_DUCK = dict(threshold=.08, ratio=2.5, attack=5, release=250)
base.X264 = "ref=4:aq-mode=3"  # keeps bits in the dark nebula gradients


def outro_chord(n, sr):
    """Sustained A-minor-9 button: soft-attack pad chord + sub root + a felt kick, ringing out."""
    np = base.np
    t = np.arange(n) / sr
    env = np.minimum(1, t / .012) * np.exp(-1.25 * t)
    chord = sum(np.sin(2 * np.pi * f * t) + .25 * np.sin(4 * np.pi * f * t) + .08 * np.sin(6 * np.pi * f * t)
                for f in (220.0, 261.63, 329.63, 392.0, 493.88)) / 5
    sub = np.sin(2 * np.pi * 55 * t) * np.exp(-1.6 * t)
    kick = np.sin(2 * np.pi * (48 * t + 5 * (1 - np.exp(-30 * t)))) * np.exp(-10 * t)
    return base.bq(chord, "lowpass", 3200) * env * .55 + sub * .45 + kick * .7


def music_post(music, events):
    """One-beat dropouts ('stop' cues from the page) so the big hit lands on near-silence;
    an 'outro' cue stops the groove on the next beat and lets a final chord ring out."""
    np, beat, sr = base.np, 60 / base.BPM, base.SR
    g, tail = np.ones(len(music)), np.zeros(len(music))
    drop = next(t for t, k, _ in events if k == "drop")
    for t, kind, _ in events:
        ramp = int(.02 * sr)
        if kind == "stop":
            a, b = int(t * sr), min(len(music), int((t + beat) * sr))
            g[a:b] = 0.12
            g[max(0, a - ramp):a] = np.linspace(1, .12, a - max(0, a - ramp))
            g[max(a, b - ramp):b] = np.linspace(.12, 1, b - max(a, b - ramp))
        elif kind == "outro":
            a = int((drop + np.ceil((t - drop) / beat) * beat) * sr)
            if a < len(music):
                g[a:] = 0
                g[a - 3 * ramp:a] *= np.linspace(1, 0, 3 * ramp)
                ch = outro_chord(len(music) - a, sr) * np.abs(music).max()
                fade = min(len(ch), int(.4 * sr))
                ch[-fade:] *= np.linspace(1, 0, fade)
                tail[a:] = ch
    return music * g + tail


base.MUSIC_POST = music_post

if __name__ == "__main__":
    base.main()
