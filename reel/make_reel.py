#!/usr/bin/env python3
"""Build the NEQO Digital "Ultra" ($150/mo) Instagram reel in the style of the earlier NEQO reel.

Pipeline: Gemini TTS voiceover -> line/word timing from speech chunks -> tightened VO -> build/timeline.js
-> scene.html rendered frame-by-frame in headless Chromium (render.cjs) -> synthesized 124 BPM tech-house
bed + SFX (events exported by the page) + ducking -> 1080x1920 30fps H.264/AAC MP4 via ffmpeg.

Usage:  GEMINI_API_KEY=... python3 reel/make_reel.py [--regen]   (--regen re-requests the voiceover)
Env:    GEMINI_TTS_MODEL (default: first working model in TTS_MODELS), GEMINI_VOICE (default Puck).
Needs:  ffmpeg, node + playwright (global install), python numpy + scipy.
"""
import base64, difflib, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.request, wave
import numpy as np
from scipy.signal import butter, lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
OUT = os.path.join(HERE, "neqo-digital-ultra-reel.mp4")
API = "https://generativelanguage.googleapis.com/v1beta"
W, H, FPS, SR = 1080, 1920, 30, 48000
VOICE = os.environ.get("GEMINI_VOICE", "Puck")
TTS_MODELS = ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
LEAD, HOLD, MAX_VO = 0.35, 2.0, 27.0
RENDER = os.path.join(HERE, "render.cjs")
# music: tempo, (bass root, chord) per bar, chord-stab sound ("saw" stabs or "pluck")
BPM, STAB = 124, "saw"
PROG = [(55.0, (220.0, 261.63, 329.63)), (43.65, (174.61, 220.0, 261.63)),
        (65.41, (196.0, 261.63, 329.63)), (49.0, (196.0, 246.94, 293.66))]

# One spoken line per scene in scene.html (matched by id). "Neeko" is the phonetic spelling of NEQO (NEE-koh).
LINES = [
    ("run", "You run the business."),
    ("who", "But who's running your marketing?"),
    ("meet", "Meet Neeko Digital Ultra."),
    ("team", "A full marketing team, working for you every month."),
    ("web", "A custom website."),
    ("seo", "Local SEO to rank higher on Google."),
    ("social", "Social media, posted for you."),
    ("report", "Plain-English reports. Monthly strategy calls."),
    ("live", "Live in fourteen days."),
    ("price", "All for just one-fifty a month."),
    ("end", "Neeko Digital. No contracts. Cancel anytime."),
]
PROMPT = """# AUDIO PROFILE: Hype announcer for a 25-second Instagram ad
### DIRECTOR'S NOTES
Style: confident, high-energy, upbeat male announcer with a smile in the voice; punchy emphasis on key words.
Pace: fast, rapid-fire delivery with only a short beat between lines.
Pronunciation: "Neeko" is pronounced NEE-koh.
### TRANSCRIPT
"""


# ---------------------------------------------------------------- Gemini
def api(url, body=None):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Set GEMINI_API_KEY to generate the Gemini voiceover.")
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def gemini_tts(text, path):
    models = [os.environ["GEMINI_TTS_MODEL"]] if os.environ.get("GEMINI_TTS_MODEL") else TTS_MODELS
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
    err = None
    for model in models:
        for attempt in range(3):
            try:
                r = api(f"{API}/models/{model}:generateContent", body)
                parts = r["candidates"][0].get("content", {}).get("parts")
                if not parts:  # e.g. finishReason OTHER
                    err = f"{model}: no audio (finishReason {r['candidates'][0].get('finishReason')})"
                    print(err); continue
                d = parts[0]["inlineData"]
                data = base64.b64decode(d["data"])
                if data[:4] == b"RIFF":
                    open(path, "wb").write(data)
                else:
                    m = re.search(r"rate=(\d+)", d.get("mimeType", ""))
                    with wave.open(path, "wb") as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(m[1]) if m else 24000); w.writeframes(data)
                print(f"Gemini TTS ok: model={model} voice={VOICE}")
                return model
            except urllib.error.HTTPError as e:
                msg = e.read()[:300]
                err = f"{model}: HTTP {e.code} {msg!r}"; print(err)
                if e.code in (429, 500, 503) and b"limit: 0" not in msg and attempt < 2:
                    time.sleep(20 * (attempt + 1)); continue
                break
    sys.exit(f"Gemini TTS failed: {err}")


def transcribe(path):
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(open(path, "rb").read()).decode()}},
                                    {"text": "Transcribe this audio verbatim. Output only the spoken words."}]}]}
    for m in ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-flash-latest"]:
        try:
            return api(f"{API}/models/{m}:generateContent", body)["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print(f"transcribe {m}: {e}")
    return None


# ---------------------------------------------------------------- VO timing
def read_wav(path):
    with wave.open(path) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        a = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
    return (a.reshape(-1, ch).mean(1) if ch > 1 else a), sr


def write_wav(path, a, sr):
    a = np.clip(a, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1 if a.ndim == 1 else a.shape[1]); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((a * 32767).astype(np.int16).tobytes())


def speech_chunks(a, sr, min_gap=0.12, min_len=0.06):
    hop = int(sr * 0.01)
    fr = a[: len(a) // hop * hop].reshape(-1, hop)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    on = db > db.max() - 38
    chunks, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            chunks.append([i * 0.01, j * 0.01]); i = j
        else:
            i += 1
    merged = []
    for c in chunks:
        if merged and c[0] - merged[-1][1] < min_gap:
            merged[-1][1] = c[1]
        else:
            merged.append(c)
    return [c for c in merged if c[1] - c[0] >= min_len]


def align(chunks, texts):
    """Split the speech chunks into one consecutive run per text (segmentation DP): each run's voiced time should
    match its syllable count at the overall speaking rate, and runs should break on clear pauses rather than short
    ones. Returns the index of the gap ending each run but the last, or None if there are fewer chunks than texts."""
    n, m = len(texts), len(chunks)
    if n == 1:
        return []
    if m < n:
        return None
    syl = [sum(syllables(w) for w in t.split()) for t in texts]
    cum = np.concatenate([[0.0], np.cumsum([e - s for s, e in chunks])])
    rate = cum[-1] / sum(syl)
    gap = [chunks[k + 1][0] - chunks[k][1] for k in range(m - 1)]

    def seg(i, a, b):  # text i spoken over chunks a..b
        return (np.log((cum[b + 1] - cum[a]) / (syl[i] * rate)) ** 2
                + sum(2.0 * max(0.0, gap[k] - 0.45) for k in range(a, b)))  # long pauses rarely sit inside a line

    INF = float("inf")
    D = [[INF] * m for _ in range(n)]
    P = [[-1] * m for _ in range(n)]
    for b in range(m):
        D[0][b] = seg(0, 0, b)
    for i in range(1, n):
        for b in range(i, m):
            for a in range(i, b + 1):
                c = D[i - 1][a - 1] + seg(i, a, b) + 2.0 * max(0.0, 0.3 - gap[a - 1])
                if c < D[i][b]:
                    D[i][b], P[i][b] = c, a
    res, b = [], m - 1
    for i in range(n - 1, 0, -1):
        b = P[i][b] - 1
        res.append(b)
    return res[::-1]


def split_spans(chunks, texts, span):
    """Return (start, end) per text within span using chunk gaps, else proportional by length."""
    cs = [c for c in chunks if c[0] >= span[0] - 1e-6 and c[1] <= span[1] + 1e-6]
    b = align(cs, texts) if cs else None
    if b is None:
        L, s0, s1 = [len(t) for t in texts], span[0], span[1]
        cut = [s0 + (s1 - s0) * sum(L[:i]) / sum(L) for i in range(len(texts) + 1)]
        return [(cut[i], cut[i + 1]) for i in range(len(texts))]
    edges = [cs[0][0]] + [x for g in b for x in (cs[g][1], cs[g + 1][0])] + [cs[-1][1]]
    return [(edges[2 * i], edges[2 * i + 1]) for i in range(len(texts))]


def syllables(w):
    if re.fullmatch(r"[A-Z]{2,4}\W*", w):  # acronyms are spelled out (S-E-O)
        return len(re.sub(r"\W", "", w))
    w = re.sub(r"[^a-z]", "", w.lower())
    n = len(re.findall(r"[aeiouy]+", w)) or 1
    return n - 1 if w.endswith("e") and n > 1 and not w.endswith(("le", "ee")) else n


def word_starts(chunks, words, span):
    """Start time per word: split the line into phrases at punctuation (aligned to pauses), then spread each
    phrase's words over its voiced time by syllable count."""
    phrases, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[,.?!]$", w):
            phrases.append(cur); cur = []
    if cur:
        phrases.append(cur)
    out = []
    for p, (s, e) in zip(phrases, split_spans(chunks, [" ".join(p) for p in phrases], span)):
        segs = [(max(a, s), min(b, e)) for a, b in chunks if b > s and a < e] or [(s, e)]
        voiced = sum(b - a for a, b in segs)
        wt = [syllables(w) + 0.5 for w in p]
        for f in np.cumsum([0] + wt[:-1]) / sum(wt):
            x = f * voiced
            for a, b in segs:
                if x < b - a:
                    out.append(a + x); break
                x -= b - a
            else:
                out.append(segs[-1][1])
    return out


def tighten(a, sr, chunks, line_gap_idx, line_gap=0.24, intra_cap=0.2, lead=0.03, tail=0.08):
    """Rebuild VO with shortened pauses. Returns new audio and a time-mapping function."""
    pieces, marks, t = [], [], 0.0
    first = max(0, chunks[0][0] - lead)
    for i, c in enumerate(chunks):
        s = first if i == 0 else c[0]
        e = c[1]
        pieces.append(a[int(s * sr): int(e * sr)])
        marks.append((s, e, t)); t += e - s
        if i < len(chunks) - 1:
            gap = chunks[i + 1][0] - e
            g = min(gap, line_gap if i in line_gap_idx else intra_cap)
            h = int(g / 2 * sr)
            pieces += [a[int(e * sr): int(e * sr) + h], a[int(chunks[i + 1][0] * sr) - h: int(chunks[i + 1][0] * sr)]]
            t += 2 * h / sr
        else:
            pieces.append(a[int(e * sr): int((e + tail) * sr)]); t += tail

    def m(x):
        for s, e, nt in marks:
            if x <= e + 1e-6:
                return nt + max(0, x - s)
        return marks[-1][2] + marks[-1][1] - marks[-1][0]
    return np.concatenate(pieces), m


# ---------------------------------------------------------------- music + SFX
def bq(x, kind, f):
    b, a = butter(2, np.array(f, float) / (SR / 2), kind)
    return lfilter(b, a, x)


def T(d):
    return np.arange(int(d * SR)) / SR


def saw(f, d, harm=8):
    t = T(d)
    return sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, harm + 1))


def placer(n):
    out = np.zeros(n)

    def add(sig, at, g=1.0):
        i = int(round(at * SR))
        if i < 0:
            sig, i = sig[-i:], 0
        k = min(len(sig), n - i)
        if k > 0:
            out[i:i + k] += g * sig[:k]
    return out, add


def synth_music(total, drop):
    """House bed at BPM over PROG: muffled pulse + pad before the drop, full groove from the drop (bar 1 = drop)."""
    rng = np.random.default_rng(5)
    out, add = placer(int((total + 1) * SR))
    beat = 60 / BPM
    t = T(.4)
    kick = np.sin(2 * np.pi * (46 * t + 5.5 * (1 - np.exp(-20 * t)))) * np.exp(-7 * t)
    kick[:120] += rng.standard_normal(120) * np.linspace(.25, 0, 120)
    kick_lp = bq(kick, "lowpass", 260)
    hat = bq(rng.standard_normal(int(.05 * SR)), "highpass", 7500) * np.exp(-90 * T(.05))
    ohat = bq(rng.standard_normal(int(.25 * SR)), "highpass", 6500) * np.exp(-15 * T(.25))
    tc = T(.22)
    clap = bq(rng.standard_normal(len(tc)), "bandpass", [900, 3500]) * (np.exp(-26 * tc) + .9 * (tc < .035) * ((tc * 1000) % 11 < 4))
    k = -int(np.ceil(drop / beat)) - 1
    while drop + k * beat < total + 1:
        b, post = drop + k * beat, k >= 0
        root, chord = PROG[(k // 4) % len(PROG)]
        if post:
            add(kick, b, .9)
            if k % 2:
                add(clap, b, .5)
            add(ohat, b + beat / 2, .2)
            for j in range(4):
                add(hat, b + j * beat / 4, .09 if j % 2 else .05)
            add(saw(root, .22, 7) * np.minimum(1, T(.22) * 300) * np.exp(-8 * T(.22)), b + beat / 2, .5)
            if STAB == "pluck":  # marimba-ish chord plucks on every offbeat
                tp = T(.3); add(sum(np.sin(2 * np.pi * f * h * tp) * .6 ** (h - 1) * np.exp(-(10 + 6 * h) * tp) for f in chord for h in (1, 2, 3, 4)), b + beat / 2, .09)
            elif k % 4 in (1, 3):
                add(bq(sum(saw(f, .17, 12) for f in chord), "lowpass", 3000) * np.exp(-14 * T(.17)), b + beat / 2, .07)
        else:
            add(kick_lp, b, .5); add(hat, b + beat / 2, .06)
        if k % 4 == 0:
            d = 4 * beat + .05; tt = T(d)
            pad = sum(saw(f * (1 + dt), d, 6) for f in chord for dt in (-.004, .004))
            pad *= np.minimum(1, tt / .3) * np.minimum(1, (d - tt) / .1)
            add(bq(pad, "lowpass", 1400 if post else 650), b, .03 if post else .05)
        k += 1
    out = out[: int(total * SR)]
    fade = int(.9 * SR)
    out[-fade:] *= np.linspace(1, 0, fade) ** 1.5
    return out / (np.abs(out).max() + 1e-9) * .9


def synth_sfx(total, events):
    rng = np.random.default_rng(9)
    out, add = placer(int((total + 1) * SR))
    for t, kind, p in events:
        p = p or 0
        if kind == "whoosh":
            d = .42; tt = T(d)
            add(bq(rng.standard_normal(len(tt)), "bandpass", [500, 6000]) * np.sin(np.pi * tt / d) ** 3, t - d * .6, .22)
        elif kind == "impact":
            d = 1.6; tt = T(d)
            boom = np.sin(2 * np.pi * (36 * tt + 4 * (1 - np.exp(-8 * tt)))) * np.exp(-3 * tt)
            crash = bq(rng.standard_normal(len(tt)), "highpass", 4000) * np.exp(-2.5 * tt) * .25
            hit = bq(rng.standard_normal(len(tt)), "lowpass", 900) * np.exp(-14 * tt) * .6
            add(boom + crash + hit, t, .55)
        elif kind == "drop":  # riser that lands on the drop
            d = 1.7; tt = T(d); r = (tt / d) ** 2
            add(bq(rng.standard_normal(len(tt)), "highpass", 1200) * r * .5 + np.sin(2 * np.pi * (180 * tt + 650 * tt ** 2 / d)) * r * .2, t - d, .5)
        elif kind == "sweep":
            d = .7; tt = T(d)
            add(bq(rng.standard_normal(len(tt)), "highpass", 3000) * (tt / d) ** 2, t, .3)
        elif kind == "pop":
            d = .09; tt = T(d)
            add(np.sin(2 * np.pi * ((650 + 90 * p) * tt + 2600 * tt ** 2)) * np.exp(-40 * tt), t, .16)
        elif kind == "tick":
            tt = T(.03)
            add(np.sin(2 * np.pi * (1800 + 100 * p) * tt) * np.exp(-150 * tt), t, .1)
        elif kind == "splash":
            d = .45; tt = T(d)
            add(bq(rng.standard_normal(len(tt)), "bandpass", [350, 2600]) * np.minimum(1, tt * 200) * np.exp(-9 * tt), t, .35)
            for j in range(5):
                tb = T(.05); add(np.sin(2 * np.pi * (500 + 160 * j) * tb * (1 + 6 * tb)) * np.exp(-60 * tb), t + .04 + j * .05, .12)
        elif kind == "thump":
            tt = T(.3); add(np.sin(2 * np.pi * (45 * tt + 6 * (1 - np.exp(-25 * tt)))) * np.exp(-12 * tt) + rng.standard_normal(len(tt)) * np.exp(-60 * tt) * .3, t, .5)
        elif kind == "glitch":
            for j in range(6):
                tt = T(.025)
                add(np.sign(np.sin(2 * np.pi * rng.uniform(200, 1400) * tt)) * .4 + rng.standard_normal(len(tt)) * .2, t + j * .045, .25)
    return out[: int(total * SR)]


# ---------------------------------------------------------------- main
def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def fetch_fonts():
    d = os.path.join(BUILD, "fonts")
    os.makedirs(d, exist_ok=True)
    if all(os.path.exists(os.path.join(d, f"Inter-{w}.ttf")) for w in (500, 600, 700, 800, 900)):
        return
    css = urllib.request.urlopen("https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700;800;900").read().decode()
    for w, url in re.findall(r"font-weight: (\d+);.*?src: url\((https://[^)]+)\)", css, re.S):
        urllib.request.urlretrieve(url, os.path.join(d, f"Inter-{w}.ttf"))


def main():
    os.makedirs(BUILD, exist_ok=True)
    fetch_fonts()
    raw = os.path.join(BUILD, "vo_gemini_raw.wav")
    texts = [t for _, t in LINES]
    if not os.path.exists(raw) or "--regen" in sys.argv:
        model = gemini_tts(PROMPT + "\n".join(texts), raw)
        heard = transcribe(raw) or ""
        norm = lambda s: re.findall(r"[a-z0-9]+", s.lower().replace("neqo", "neeko"))
        ratio = difflib.SequenceMatcher(None, norm(" ".join(texts)), norm(heard)).ratio()
        print(f"VO transcript ({ratio:.0%} match): {heard}")
        json.dump({"model": model, "voice": VOICE, "transcript": heard, "match": ratio},
                  open(os.path.join(BUILD, "tts_meta.json"), "w"), indent=1)
    a, sr = read_wav(raw)
    chunks = speech_chunks(a, sr)
    print(f"raw VO {len(a) / sr:.2f}s, {len(chunks)} speech chunks")
    lb = align(chunks, texts)
    if lb is None:
        sys.exit("Not enough pauses to align the script lines; re-run with --regen.")
    idx = [-1] + lb + [len(chunks) - 1]
    spans = [(chunks[idx[i] + 1][0], chunks[idx[i + 1]][1]) for i in range(len(texts))]
    vo, m = tighten(a, sr, chunks, set(lb))
    vo_len = len(vo) / sr
    tempo = min(max(1.0, vo_len / MAX_VO), 1.25)
    tight = os.path.join(BUILD, "vo_tight.wav")
    vo_t = os.path.join(BUILD, "vo_final.wav")
    write_wav(tight, vo, sr)
    run(["ffmpeg", "-v", "error", "-y", "-i", tight, "-af", f"atempo={tempo:.4f}", "-ar", str(SR), vo_t])
    vo_len /= tempo
    f = lambda x: round(LEAD + m(x) / tempo, 3)
    lines = [{"id": lid, "text": text, "t0": f(sp[0]), "t1": f(sp[1]), "w": [f(x) for x in word_starts(chunks, text.split(), sp)]}
             for (lid, text), sp in zip(LINES, spans)]
    total = round(min(30.0, LEAD + vo_len + HOLD), 3)
    print(f"VO {vo_len:.2f}s (tempo {tempo:.3f}); reel {total:.2f}s; line starts:", ", ".join(f"{l['t0']:.2f}" for l in lines))
    open(os.path.join(BUILD, "timeline.js"), "w").write("window.TL = " + json.dumps({"total": total, "lines": lines}) + ";\n")

    frames = os.path.join(BUILD, "frames")
    shutil.rmtree(frames, ignore_errors=True); os.makedirs(frames)
    npm_root = subprocess.check_output(["npm", "root", "-g"], text=True).strip()
    run(["node", RENDER, os.path.join(HERE, "scene.html"), frames, str(FPS), str(total), "4"],
        env={**os.environ, "NODE_PATH": npm_root})
    events = json.load(open(os.path.join(BUILD, "sfx.json")))
    drop = next(t for t, k, _ in events if k == "drop")
    music, sfx = os.path.join(BUILD, "music.wav"), os.path.join(BUILD, "sfx.wav")
    write_wav(music, synth_music(total, drop), SR)
    write_wav(sfx, synth_sfx(total, events), SR)

    fc = (f"[1:a]adelay={int(LEAD * 1000)}:all=1,apad,highpass=f=90,equalizer=f=3200:t=q:w=1.2:g=2.5,"
          f"acompressor=threshold=0.1:ratio=3:attack=5:release=90:makeup=1.6,asplit=2[vo][sc];"
          f"[2:a]volume=0.42[mu];[mu][sc]sidechaincompress=threshold=0.035:ratio=5:attack=8:release=260[duck];"
          f"[vo][duck][3:a]amix=inputs=3:duration=first:normalize=0,atrim=0:{total:.3f},"
          f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample={SR},aformat=channel_layouts=stereo[a];"
          f"[0:v]scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[v]")
    run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(frames, "f_%05d.jpg"),
         "-i", vo_t, "-i", music, "-i", sfx, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-r", str(FPS),
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", OUT])
    print("wrote", OUT, f"{os.path.getsize(OUT) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
