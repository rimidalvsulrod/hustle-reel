#!/usr/bin/env python3
"""Build the NEQO Digital 16:9 brand ad ("Full Stop").

Reuses the shared reel pipeline (../reel/make_reel.py: Gemini TTS, VO-synced timeline, Chromium frame render,
mix, ffmpeg export) at 1920x1080 with this folder's scene.html, a quiet custom pulse and extra Foley-style SFX.

Usage:  GEMINI_API_KEY=... python3 neqo16x9/make_ad.py [--regen] [--timeline-only]
"""
import importlib.util, os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("reel_pipeline", os.path.join(HERE, "..", "reel", "make_reel.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
np = base.np

base.HERE, base.BUILD, base.OUT = HERE, os.path.join(HERE, "build"), os.path.join(HERE, "neqo-digital-16x9-ad.mp4")
base.W, base.H = 1920, 1080
base.HOLD, base.MAX_VO, base.MAX_TOTAL = 2.6, 31.0, 34.0
os.environ.setdefault("FRAME_FMT", "png")
# One spoken line per scene in scene.html (matched by id). "Neeko" is the phonetic spelling of NEQO (NEE-koh).
base.LINES = [
    ("stopped", "You stopped."),
    ("job", "That's the job."),
    ("ad", "This is an ad."),
    ("made", "Made from type, timing, and one orange dot."),
    ("picture", "Now picture your business in it."),
    ("trades", "Roofers. Plumbers. H-VAC. Dentists. Med spas."),
    ("likethis", "Neeko makes ads like this, for local service businesses."),
    ("website", "And the website they land on."),
    ("services", "Local SEO. Social. Paid ads."),
    ("terms", "One subscription. No contracts."),
    ("live", "Live in fourteen days."),
    ("end", "Start at Neeko digital dot com."),
]
base.PROMPT = """# AUDIO PROFILE: Confident, warm male announcer for a 30-second brand film for a design studio
### DIRECTOR'S NOTES
Style: calm, certain and warm, with a quiet smile in the voice. Never smug, never sarcastic, never shouty. Crisp diction; land the last word of every line like a full stop.
Pace: brisk and rhythmic. Read every line of the transcript as its own sentence and leave a clear, short pause (about half a second) after each line; never run two lines together. In the list lines, give each item its own short beat.
Pronunciation: "Neeko" is pronounced NEE-koh. "H-VAC" is said "H-vac" (aitch-vack). "SEO" is spelled out: S-E-O. "dot com" as normal.
### TRANSCRIPT
"""
base.BPM = 120
base.CRF, base.MUSIC_GAIN = 16, 0.2  # the pulse sits far under the voice
base.SFX_GAIN = {"whoosh": .5, "impact": .55}
base.DUCK = dict(threshold=.05, ratio=2, attack=15, release=700)
base.SFX_DUCK = dict(threshold=.1, ratio=2, attack=5, release=200)
base.X264 = "ref=4:aq-mode=3:deblock=-1,-1"


def pulse(total, drop):
    """A quiet, dry 120 BPM pulse: soft sub kick on the beat + faint closed hats on 8ths, from the first cut on.
    'mute' cues from the page (p = seconds) drop it out; 'outro' ends it with one soft kick and a low chord."""
    sr, beat = base.SR, 60 / base.BPM
    n = int((total + 1) * sr)
    out, add = base.placer(n)
    rng = np.random.default_rng(3)
    tt = base.T(.32)
    kick = np.sin(2 * np.pi * (44 * tt + 9 * (1 - np.exp(-28 * tt)))) * np.exp(-11 * tt)
    th = base.T(.035)
    hat = base.bq(rng.standard_normal(len(th)), "highpass", 7500) * np.exp(-120 * th)
    k = 0
    while drop + k * beat / 2 < total:
        t = drop + k * beat / 2
        if k % 2 == 0:
            add(kick, t, .9)
        add(hat, t, .12 if k % 2 else .07)
        k += 1
    return out[: int(total * sr)] / (np.abs(out).max() + 1e-9) * .9


def music_post(music, events):
    sr = base.SR
    g, tail = np.ones(len(music)), np.zeros(len(music))
    ramp = int(.015 * sr)
    for t, kind, p in events:
        if kind == "mute":
            a, b = int(t * sr), min(len(music), int((t + p) * sr))
            g[a:b] = 0
            g[max(0, a - ramp):a] *= np.linspace(1, 0, a - max(0, a - ramp))
            g[b:b + ramp] *= np.linspace(0, 1, len(g[b:b + ramp]))
        elif kind == "outro":
            a = int(t * sr)
            g[a:] = 0
            g[max(0, a - ramp):a] *= np.linspace(1, 0, a - max(0, a - ramp))
            n = len(music) - a
            if n > 0:
                tt = np.arange(n) / sr
                kick = np.sin(2 * np.pi * (44 * tt + 9 * (1 - np.exp(-28 * tt)))) * np.exp(-9 * tt)
                chord = sum(np.sin(2 * np.pi * f * tt) for f in (110.0, 164.81, 220.0, 277.18)) / 4
                chord = base.bq(chord, "lowpass", 1200) * np.minimum(1, tt / .02) * np.exp(-1.1 * tt) * .35
                tail[a:] = (kick * .9 + chord) * np.abs(music).max()
                f = min(n, int(.3 * sr)); tail[-f:] *= np.linspace(1, 0, f)
    return music * g + tail


_orig_sfx = base.synth_sfx


def foley(total, events):
    """Extra dry, woody SFX for this piece on top of the shared kit."""
    out = _orig_sfx(total, [e for e in events if e[1] not in ("ratchet", "thock", "clatter", "blip", "knock", "type", "drop")])  # no stock riser
    n = len(out)
    rng = np.random.default_rng(21)
    T, bq, sr = base.T, base.bq, base.SR

    def add(sig, at, g):
        i = int(round(at * sr))
        if i < 0: sig, i = sig[-i:], 0
        k = min(len(sig), n - i)
        if k > 0: out[i:i + k] += g * sig[:k]

    for t, kind, p in events:
        p = p or 0
        if kind == "ratchet":  # fast plastic scroll clicks over p seconds, slowing down
            m = int(p / .028)
            for j in range(m):
                q = j / max(1, m - 1); tb = T(.012)
                add(bq(rng.standard_normal(len(tb)), "bandpass", [2500, 7000]) * np.exp(-400 * tb), t + p * (q ** 1.6), .16 * (1 - .6 * q))
        elif kind == "thock":  # dull woody knock: ball landing
            tt = T(.18)
            body = np.sin(2 * np.pi * (180 + 40 * p) * tt * (1 - .3 * tt)) * np.exp(-34 * tt)
            add(body + .4 * np.sin(2 * np.pi * 70 * tt) * np.exp(-22 * tt) + bq(rng.standard_normal(len(tt)), "lowpass", 2500) * np.exp(-90 * tt) * .5, t, .25 * (1 - .25 * min(p, 3)))
        elif kind == "knock":  # small wood tick: bounces / steps
            tt = T(.06)
            add(np.sin(2 * np.pi * (900 + 120 * p) * tt) * np.exp(-90 * tt) + bq(rng.standard_normal(len(tt)), "bandpass", [1500, 5000]) * np.exp(-160 * tt) * .5, t, .14)
        elif kind == "type":  # soft key tick
            tt = T(.025)
            add(bq(rng.standard_normal(len(tt)), "bandpass", [1800, 6000]) * np.exp(-260 * tt), t, .09)
        elif kind == "clatter":  # letters falling: scattered knocks over p seconds
            for j in range(9):
                tt = T(.05); at = t + rng.uniform(0, p)
                add(np.sin(2 * np.pi * rng.uniform(500, 1400) * tt) * np.exp(-100 * tt), at, .1)
        elif kind == "blip":  # two-tone phone blip
            for j, f in enumerate((1320, 1760)):
                tt = T(.09); add(np.sin(2 * np.pi * f * tt) * np.minimum(1, tt / .005) * np.exp(-30 * tt), t + j * .1, .08)
    return out


base.synth_music, base.MUSIC_POST, base.synth_sfx = pulse, music_post, foley

_orig_prepare = base.prepare
# Word onsets verified on the energy envelope of build/vo_final.wav (whisper merges "medspas"/"nicodigital", runs early in "made").
FIXED = {"made": {1: 3.24, 2: 3.55, 3: 4.18}, "trades": {4: 11.45, 5: 11.77}, "likethis": {4: 13.36, 5: 13.92},
         "end": {1: 24.02, 2: 24.30, 3: 24.66, 4: 25.0, 5: 25.24}}


def refined_prepare():
    """Run the shared prepare(), then sharpen mid-line word onsets: whisper word starts where they match the script,
    energy onsets for words whisper merged. Line starts keep the pipeline's chunk-based onsets (more reliable)."""
    import difflib, json, re, wave
    total = _orig_prepare()
    tl_path, vo = os.path.join(base.BUILD, "timeline.js"), os.path.join(base.BUILD, "vo_final.wav")
    TL = json.loads(open(tl_path).read().split("=", 1)[1].rstrip().rstrip(";"))
    cache = os.path.join(base.BUILD, "whisper_words.json")
    if not os.path.exists(cache) or os.path.getmtime(cache) < os.path.getmtime(vo):
        from faster_whisper import WhisperModel
        segs, _ = WhisperModel("small.en", device="cpu", compute_type="int8").transcribe(vo, word_timestamps=True)
        json.dump([(w.start + base.LEAD, w.end + base.LEAD, w.word.strip()) for s in segs for w in s.words], open(cache, "w"))
    ww = json.load(open(cache))
    w = wave.open(vo); a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float); sr = w.getframerate()
    hop = sr // 100; db = 20 * np.log10(np.sqrt(np.convolve(a ** 2, np.ones(hop) / hop, "same")[::hop]) / 32768 + 1e-9)
    onsets = [i * .01 + base.LEAD for i in range(6, len(db)) if db[i] > -35 and db[i - 1] <= -35 and max(db[i - 6:i - 1]) < -45]
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower().replace("neeko", "nico").replace("hvac", "hvac"))
    for line in TL["lines"]:
        toks = line["text"].split()
        cand = [x for x in ww if line["t0"] - .3 <= x[0] <= line["t1"] + .2]
        sm = difflib.SequenceMatcher(None, [norm(t) for t in toks], [norm(x[2]) for x in cand])
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                i, j = blk.a + k, blk.b + k
                if i > 0 and abs(cand[j][0] - line["w"][i]) < .4:
                    line["w"][i] = round(cand[j][0], 3)
        matched = {blk.a + k for blk in sm.get_matching_blocks() for k in range(blk.size)}
        for i in range(1, len(toks)):
            if i not in matched:
                near = [o for o in onsets if abs(o - line["w"][i]) < .3 and o > line["w"][i - 1] + .08]
                if near: line["w"][i] = round(min(near, key=lambda o: abs(o - line["w"][i])), 3)
        for i, t in FIXED.get(line["id"], {}).items():  # onsets read off the VO energy envelope where whisper is unreliable
            line["w"][i] = t
        for i in range(1, len(toks)):  # keep strictly increasing
            line["w"][i] = max(line["w"][i], line["w"][i - 1] + .06)
    open(tl_path, "w").write("window.TL = " + json.dumps(TL) + ";\n")
    for l in TL["lines"]:
        print(f"{l['id']:9s} " + " ".join(f"{x:.2f}" for x in l["w"]))
    return total


base.prepare = refined_prepare

if __name__ == "__main__":
    base.main()
