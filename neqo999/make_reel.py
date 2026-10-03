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
base.LINES = [
    ("hook", "Want your own marketing team?"),
    ("meet", "Meet Ultra. Your team, assembled."),
    ("website", "Your website, built and updated."),
    ("seo", "Local SEO to climb Google."),
    ("social", "Social posts, handled for you."),
    ("reviews", "Review requests on autopilot."),
    ("report", "A plain-English monthly report."),
    ("strategy", "Strategy calls. A real person, anytime."),
    ("price", "Your marketing team for nine hundred ninety-nine dollars a month."),
    ("end", "Neeko Digital. Plans from two hundred ninety-nine dollars a month. No contracts."),
]
base.PROMPT = """# AUDIO PROFILE: Premium, high-energy announcer for a 25-second Instagram ad for a marketing agency
### DIRECTOR'S NOTES
Style: confident, upbeat and polished, with a warm smile in the voice; crisp diction; punchy emphasis on the key words.
Pace: fast and energetic. Read every line of the transcript as its own sentence and leave a clear, short pause (about half a second) after each line; never run two lines together.
Numbers: say both prices in full exactly as written, always including the words "hundred" and "dollars": "nine hundred ninety-nine dollars" and "two hundred ninety-nine dollars".
Pronunciation: "Neeko" is pronounced NEE-koh. "SEO" is spelled out: S-E-O.
### TRANSCRIPT
"""

# Bright 124 BPM future-house in A major (Amaj7 - F#m9 - Dmaj9 - E6sus) with plucked chords.
base.BPM, base.STAB = 124, "pluck"
base.PROG = [(55.0, (220.0, 277.18, 329.63, 415.30)), (46.25, (185.0, 220.0, 277.18, 329.63)),
             (73.42, (185.0, 220.0, 277.18, 329.63)), (41.20, (220.0, 246.94, 277.18, 329.63))]
base.CRF, base.MUSIC_GAIN = 16, 0.5  # low CRF: the light gradients band at higher values
base.SFX_GAIN = {"drop": .6, "sweep": .5, "shimmer": .6, "impact": .8, "thump": .8, "glitch": .8}
base.X264 = "ref=4:aq-mode=3"  # keeps bits in the flat pastel gradients
base.DUCK = dict(threshold=.06, ratio=3, attack=10, release=420)
base.SFX_DUCK = dict(threshold=.08, ratio=2.5, attack=5, release=250)


def outro_chord(n, sr):
    """Sustained A-major-9 button: soft-attack pad chord + sub root + a felt kick, ringing out."""
    np = base.np
    t = np.arange(n) / sr
    env = np.minimum(1, t / .012) * np.exp(-1.25 * t)
    chord = sum(np.sin(2 * np.pi * f * t) + .25 * np.sin(4 * np.pi * f * t) + .08 * np.sin(6 * np.pi * f * t)
                for f in (220.0, 277.18, 329.63, 415.30, 493.88)) / 5
    sub = np.sin(2 * np.pi * 55 * t) * np.exp(-1.6 * t)
    kick = np.sin(2 * np.pi * (48 * t + 5 * (1 - np.exp(-30 * t)))) * np.exp(-10 * t)
    return base.bq(chord, "lowpass", 3200) * env * .55 + sub * .45 + kick * .7


def music_post(music, events):
    """One-beat dropouts ('stop' cues from the page) so the price slam lands on near-silence;
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
    import sys
    if "--tts-only" in sys.argv:  # generate + transcribe the voiceover without rendering
        os.makedirs(base.BUILD, exist_ok=True)
        raw = os.path.join(base.BUILD, "vo_gemini_raw.wav")
        texts = [t for _, t in base.LINES]
        model = base.gemini_tts(base.PROMPT + "\n".join(texts), raw)
        print("model:", model, "| transcript:", base.transcribe(raw))
    else:
        base.main()
