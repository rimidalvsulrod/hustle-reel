#!/usr/bin/env python3
"""Build the NEQO Digital "Ultra" ($150/mo) Instagram reel.

Pipeline: Gemini TTS voiceover -> detect speech chunks -> align script lines/beats
-> tighten pauses -> ASS motion-graphics overlays synced to the VO -> synthesized
beat + ducking -> 1080x1920 H.264 MP4.

Usage:
  GEMINI_API_KEY=... python3 reel/make_reel.py          # real Gemini voiceover
  python3 reel/make_reel.py --fake-tts                   # pipeline test with tone bursts
Env: GEMINI_TTS_MODEL (optional model override), GEMINI_VOICE (default Puck).
"""
import base64, json, math, os, re, subprocess, sys, time, urllib.error, urllib.request, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
OUT = os.path.join(HERE, "neqo-digital-ultra-reel.mp4")
W, H, FPS = 1080, 1920, 30
SR = 48000
VOICE = os.environ.get("GEMINI_VOICE", "Puck")

# Each scene = one spoken line. Each beat = one on-screen card (fast cut) synced to its spoken fragment.
# t: main text (\N = newline, *word* = highlight), k: kicker above, sub: line below, check: tick icon.
SCENES = [
    [dict(s="Plumbers.", t="PLUMBERS"), dict(s="Roofers.", t="ROOFERS"), dict(s="Dentists.", t="DENTISTS"),
     dict(s="HVAC.", t="HVAC"), dict(s="Electricians.", t="ELECTRICIANS")],
    [dict(s="Stop losing jobs to the competition.", t="STOP LOSING\\N*JOBS*", sub="TO THE COMPETITION")],
    [dict(s="Meet Neqo Digital's Ultra plan.", k="NEQO DIGITAL", t="THE *ULTRA*\\NPLAN")],
    [dict(s="A full marketing team, working on your business every month.", t="A FULL\\N*MARKETING*\\NTEAM",
          sub="WORKING FOR YOU EVERY MONTH")],
    [dict(s="A custom website.", t="CUSTOM\\N*WEBSITE*", check=True)],
    [dict(s="Local SEO, to rank higher on Google.", k="LOCAL SEO", t="RANK HIGHER\\NON *GOOGLE*", check=True)],
    [dict(s="Social media, posted for you.", t="SOCIAL MEDIA\\N*POSTED*\\NFOR YOU", check=True)],
    [dict(s="A plain-English report,", t="MONTHLY\\N*REPORT*", sub="IN PLAIN ENGLISH", check=True),
     dict(s="and a strategy call, every month.", t="STRATEGY\\N*CALL*", sub="EVERY MONTH", check=True)],
    [dict(s="All for just one hundred fifty dollars a month.", k="ALL FOR JUST", price=True)],
    [dict(s="No contracts.", t="NO\\N*CONTRACTS*"), dict(s="Cancel anytime.", t="CANCEL\\N*ANYTIME*")],
    [dict(s="Neqo Digital. Let's get you more customers.", end=True)],
]
LINES = [" ".join(b["s"] for b in sc) for sc in SCENES]
STYLE = ("Say the following in a confident, energetic, high-energy TV ad announcer voice. "
         "Punchy, upbeat and fast-paced. Leave a short pause between each line:\n")

# ASS colours are &HBBGGRR&
NAVY, BLUE, YELLOW, WHITE, BLACK, RED = "&H2A0E0A&", "&HFF4F1F&", "&H38DCFF&", "&HFFFFFF&", "&H000000&", "&H3B3BFF&"
# (bg, fg, highlight, shadow)
SCHEMES = [(BLUE, WHITE, YELLOW, NAVY), (YELLOW, NAVY, BLUE, WHITE), (NAVY, WHITE, YELLOW, BLUE), (RED, WHITE, YELLOW, NAVY)]
FONT = "Liberation Sans"


# ---------------------------------------------------------------- TTS
def http_json(url, key, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def tts_models(key):
    if os.environ.get("GEMINI_TTS_MODEL"):
        return [os.environ["GEMINI_TTS_MODEL"]]
    try:
        names = [m["name"].split("/")[-1] for m in
                 http_json("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000", key)["models"]
                 if "tts" in m["name"]]
    except Exception as e:
        print("model list failed:", e)
        names = []
    names = sorted(set(names) | {"gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"},
                   key=lambda n: ("flash" not in n, "preview" in n, n), reverse=False)
    return names


def gemini_tts(prompt, path):
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("Set GEMINI_API_KEY (Google AI Studio key) to generate the Gemini voiceover.")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
    last = None
    for model in tts_models(key):
        for attempt in range(3):
            try:
                print(f"Gemini TTS: model={model} voice={VOICE}")
                r = http_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", key, body)
                part = r["candidates"][0]["content"]["parts"][0]["inlineData"]
                rate = int(re.search(r"rate=(\d+)", part.get("mimeType", "")).group(1)) if "rate=" in part.get("mimeType", "") else 24000
                pcm = base64.b64decode(part["data"])
                with wave.open(path, "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
                return model
            except urllib.error.HTTPError as e:
                last = f"{model}: HTTP {e.code} {e.read()[:300]!r}"
                print(last)
                if e.code == 429 and attempt < 2:
                    time.sleep(30 * (attempt + 1)); continue
                break
            except Exception as e:
                last = f"{model}: {e}"; print(last); break
    sys.exit(f"Gemini TTS failed: {last}")


def fake_tts(path):
    """Tone bursts shaped like the script (for testing sync without an API key)."""
    sr, out = 24000, []
    for li, sc in enumerate(SCENES):
        for bi, b in enumerate(sc):
            d = len(b["s"]) * 0.065
            t = np.arange(int(d * sr)) / sr
            out += [0.3 * np.sin(2 * np.pi * (180 + 40 * li) * t) * np.minimum(1, np.minimum(t, d - t) * 40),
                    np.zeros(int((0.18 if bi < len(sc) - 1 else 0.6) * sr))]
    a = (np.concatenate(out) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(a.tobytes())


# ---------------------------------------------------------------- audio helpers
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
    """Pick which inter-chunk gaps separate consecutive texts. Returns list of gap indices or None."""
    n = len(texts)
    if n == 1:
        return []
    gaps = [(chunks[i][1], chunks[i + 1][0]) for i in range(len(chunks) - 1)]
    if len(gaps) < n - 1:
        return None
    s0, s1 = chunks[0][0], chunks[-1][1]
    L = [len(t) for t in texts]
    E = [s0 + (s1 - s0) * sum(L[: i + 1]) / sum(L) for i in range(n - 1)]
    cost = lambda i, j: abs((gaps[j][0] + gaps[j][1]) / 2 - E[i]) - 1.2 * min(gaps[j][1] - gaps[j][0], 0.7)
    G, INF = len(gaps), float("inf")
    dp = [[INF] * G for _ in range(n - 1)]
    bk = [[-1] * G for _ in range(n - 1)]
    for j in range(G):
        dp[0][j] = cost(0, j)
    for i in range(1, n - 1):
        best, arg = INF, -1
        for j in range(G):
            if j - 1 >= 0 and dp[i - 1][j - 1] < best:
                best, arg = dp[i - 1][j - 1], j - 1
            if best < INF:
                dp[i][j], bk[i][j] = best + cost(i, j), arg
    j = min(range(G), key=lambda j: dp[n - 2][j])
    if dp[n - 2][j] == INF:
        return None
    res = [j]
    for i in range(n - 2, 0, -1):
        j = bk[i][j]; res.append(j)
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


def tighten(a, sr, chunks, line_gap_idx, line_gap=0.26, intra_cap=0.3, lead=0.03, tail=0.06):
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


# ---------------------------------------------------------------- music
def synth_music(dur, cuts, sr=SR):
    n = int(dur * sr)
    out = np.zeros(n, np.float32)
    rng = np.random.default_rng(7)
    beat = 60 / 126

    def add(sig, at, g=1.0):
        i = int(at * sr)
        if i >= n:
            return
        k = min(len(sig), n - i)
        out[i:i + k] += g * sig[:k]

    t = np.arange(int(0.4 * sr)) / sr
    kick = np.sin(2 * np.pi * (45 * t + (110 / 22) * (1 - np.exp(-22 * t)))) * np.exp(-7 * t)
    tn = np.arange(int(0.06 * sr)) / sr
    hat = np.diff(rng.standard_normal(len(tn) + 1)) * np.exp(-70 * tn) * 0.25
    ts = np.arange(int(0.2 * sr)) / sr
    snare = rng.standard_normal(len(ts)) * np.exp(-22 * ts) * 0.45 + np.sin(2 * np.pi * 190 * ts) * np.exp(-30 * ts) * 0.3
    roots = [55.0, 43.65, 65.41, 49.0]
    k, b = 0, 0.0
    while b < dur:
        add(kick, b, 0.9)
        add(hat, b + beat / 2)
        if k % 2 == 1:
            add(snare, b)
        f = roots[(k // 4) % 4]
        tb = np.arange(int(beat * sr)) / sr
        env = np.minimum(1, tb * 30) * (0.35 + 0.65 * np.clip((tb - 0.06) / 0.15, 0, 1))  # sidechain pump
        add((np.sin(2 * np.pi * f * tb) + 0.3 * np.sin(4 * np.pi * f * tb)) * env * 0.35 * np.exp(-1.5 * tb), b)
        k += 1; b += beat
    tw = np.arange(int(0.25 * sr)) / sr  # impact on each cut
    hit = rng.standard_normal(len(tw)) * np.exp(-18 * tw) * 0.25 + np.sin(2 * np.pi * 60 * tw) * np.exp(-9 * tw) * 0.6
    for c in cuts:
        add(hit, c)
    return out / (np.abs(out).max() + 1e-9) * 0.9


# ---------------------------------------------------------------- ASS overlays
def ts(x):
    cs = int(round(x * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


RECT = "m 0 0 l 1080 0 1080 1920 0 1920"
CIRCLE = "m 50 0 b 78 0 100 22 100 50 b 100 78 78 100 50 100 b 22 100 0 78 0 50 b 0 22 22 0 50 0"
CHECK = "m 18 50 l 32 36 l 44 48 l 70 22 l 84 36 l 44 76"


def hl(text, fg, hlc):
    return re.sub(r"\*(.+?)\*", lambda m: f"{{\\c{hlc}}}{m.group(1)}{{\\c{fg}}}", text)


def text_size(text, base, maxw=960, k=0.68):
    longest = max(len(re.sub(r"\*", "", l)) for l in text.split("\\N"))
    return int(min(base, maxw / (k * longest)))


def beat_events(b, s, e, idx):
    ev = []
    D = lambda layer, tags, body, s0=s, e0=e: ev.append(f"Dialogue: {layer},{ts(s0)},{ts(e0)},Default,,0,0,0,,{{{tags}}}{body}")
    if b.get("end"):
        bg, fg, hlc, sh = NAVY, WHITE, YELLOW, BLUE
    elif b.get("price"):
        bg, fg, hlc, sh = YELLOW, NAVY, BLUE, WHITE
    else:
        bg, fg, hlc, sh = SCHEMES[idx % len(SCHEMES)]
    ms = int((e - s) * 1000)
    D(0, f"\\an7\\pos(0,0)\\bord0\\shad0\\c{bg}\\p1", RECT)
    # moving diagonal stripes for energy
    D(1, f"\\an7\\bord0\\shad0\\c{sh}\\alpha&HC8&\\move(-900,0,700,0)\\p1", "m 0 0 l 260 0 l 760 1920 l 500 1920")
    D(1, f"\\an7\\bord0\\shad0\\c{hlc}\\alpha&HD8&\\move(-500,0,1300,0)\\p1", "m 0 0 l 90 0 l 590 1920 l 500 1920")
    # cut flash
    D(9, "\\an7\\pos(0,0)\\bord0\\shad0\\c&HFFFFFF&\\alpha&H50&\\fad(0,130)\\p1", RECT, s, min(e, s + 0.13))
    pop = f"\\fscx135\\fscy135\\t(0,110,\\fscx100\\fscy100)\\t(110,{ms},\\fscx107\\fscy107)"
    base = f"\\an5\\bord0\\shad9\\4c{sh}\\4a&H00&\\fn{FONT}\\b1"
    cy = 980
    if b.get("end"):
        D(3, f"{base}\\pos(540,700)\\fs150\\c{WHITE}{pop}", "NEQO")
        D(3, f"{base}\\pos(540,840)\\fs92\\c{WHITE}\\fsp12{pop}", "DIGITAL")
        D(2, f"\\an5\\pos(540,955)\\bord0\\shad0\\c{YELLOW}\\fscx0\\t(80,300,\\fscx100)\\p1", "m 0 0 l 700 0 700 12 0 12")
        D(3, f"{base}\\pos(540,1100)\\fs170\\c{YELLOW}{pop}", "$150/mo.")
        D(3, f"{base}\\pos(540,1270)\\fs104\\c{WHITE}{pop}", "No contracts.")
        D(3, f"\\an5\\pos(540,1440)\\bord0\\shad0\\fn{FONT}\\fs46\\c{WHITE}\\alpha&H40&\\fad(300,0)",
          "WEBSITES  •  LOCAL SEO  •  SOCIAL")
        return ev
    D(4, f"\\an8\\pos(540,250)\\bord0\\shad0\\fn{FONT}\\b1\\fs44\\fsp10\\c{fg}\\alpha&H60&", "NEQO DIGITAL")
    if b.get("price"):
        D(3, f"{base}\\pos(540,700)\\fs90\\c{fg}{pop}", "ALL FOR JUST")
        D(3, f"{base}\\pos(540,990)\\fs330\\c{hlc}\\frz-4{pop}", "$150")
        D(3, f"{base}\\pos(540,1260)\\fs150\\c{fg}\\frz-4{pop}", "/MO")
        return ev
    fs = text_size(b["t"], 170)
    nl = b["t"].count("\\N") + 1
    th = nl * fs * 1.12
    top, bot = cy - th / 2, cy + th / 2
    D(3, f"{base}\\pos(540,{cy})\\fs{fs}\\c{fg}\\frz-3{pop}", hl(b["t"], fg, hlc))
    if b.get("k"):
        D(3, f"{base}\\shad6\\pos(540,{int(top - 60)})\\fs76\\fsp6\\c{hlc}{pop}", b["k"])
        top -= 120
    if b.get("sub"):
        D(3, f"{base}\\shad6\\pos(540,{int(bot + 75)})\\fs{text_size(b['sub'], 66, 960, 0.66)}\\c{fg}\\fad(120,0)", b["sub"])
    if b.get("check"):
        y = int(top - 150)
        cpop = "\\fscx0\\fscy0\\t(40,200,\\fscx210\\fscy210)\\t(200,260,\\fscx190\\fscy190)"
        D(2, f"\\an5\\pos(540,{y})\\bord0\\shad0\\c{hlc}{cpop}\\p1", CIRCLE)
        D(3, f"\\an5\\pos(540,{y})\\bord0\\shad0\\c{bg}{cpop}\\p1", CHECK)
    return ev


def write_ass(path, beats):
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},120,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for i, (b, s, e) in enumerate(beats):
        ev += beat_events(b, s, e, i)
    open(path, "w").write(hdr + "\n".join(ev) + "\n")


# ---------------------------------------------------------------- main
def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main():
    fake = "--fake-tts" in sys.argv
    os.makedirs(BUILD, exist_ok=True)
    raw = os.path.join(BUILD, "vo_fake.wav" if fake else "vo_gemini_raw.wav")
    if fake:
        fake_tts(raw)
    elif not os.path.exists(raw) or "--regen" in sys.argv:
        model = gemini_tts(STYLE + "\n".join(LINES), raw)
        json.dump({"model": model, "voice": VOICE}, open(os.path.join(BUILD, "tts_meta.json"), "w"))
    a, sr = read_wav(raw)
    chunks = speech_chunks(a, sr)
    print(f"raw VO {len(a) / sr:.2f}s, {len(chunks)} speech chunks")

    # line-level alignment, then tighten pauses
    lb = align(chunks, LINES)
    if lb is None:
        print("WARNING: not enough pauses for line alignment; using proportional timing")
        line_spans = split_spans(chunks, LINES, (chunks[0][0], chunks[-1][1]))
        vo, m = a[int(max(0, chunks[0][0] - 0.03) * sr): int((chunks[-1][1] + 0.06) * sr)], lambda x: x - max(0, chunks[0][0] - 0.03)
    else:
        idx = [-1] + lb + [len(chunks) - 1]
        line_spans = [(chunks[idx[i] + 1][0], chunks[idx[i + 1]][1]) for i in range(len(LINES))]
        vo, m = tighten(a, sr, chunks, set(lb))
    beat_spans = []
    for sc, sp in zip(SCENES, line_spans):
        beat_spans += split_spans(chunks, [b["s"] for b in sc], sp)
    beat_starts = [m(s) for s, _ in beat_spans]
    vo_len = len(vo) / sr

    # keep the whole reel inside 15-30s
    MAX_VO = 27.0
    tempo = 1.0
    if vo_len > MAX_VO:
        tempo = min(vo_len / MAX_VO, 1.3)
        print(f"VO {vo_len:.2f}s too long -> atempo {tempo:.3f}")
    vo_path = os.path.join(BUILD, "vo_tight.wav")
    write_wav(vo_path, vo, sr)
    vo_t = os.path.join(BUILD, "vo_tempo.wav")
    run(["ffmpeg", "-y", "-i", vo_path, "-af", f"atempo={tempo:.4f}", "-ar", str(SR), vo_t])
    vo_len /= tempo
    beat_starts = [x / tempo for x in beat_starts]

    LEAD, HOLD = 0.25, 1.8
    total = min(30.0, max(15.0, LEAD + vo_len + HOLD))
    flat = [b for sc in SCENES for b in sc]
    starts = [0.0] + [max(0.0, LEAD + x - 0.06) for x in beat_starts[1:]]
    beats = [(b, starts[i], starts[i + 1] if i + 1 < len(flat) else total) for i, b in enumerate(flat)]
    print(f"reel length {total:.2f}s; cuts:", ", ".join(f"{s:.2f}" for _, s, _ in beats))

    ass = os.path.join(BUILD, "overlay.ass")
    write_ass(ass, beats)
    music = os.path.join(BUILD, "music.wav")
    write_wav(music, synth_music(total, [s for _, s, _ in beats]), SR)

    fc = (f"[1:a]adelay={int(LEAD * 1000)}:all=1,apad,acompressor=threshold=0.1:ratio=3:attack=5:release=80,"
          f"volume=1.6,asplit=2[vo][sc];"
          f"[2:a]volume=0.22[mu];[mu][sc]sidechaincompress=threshold=0.04:ratio=5:attack=10:release=250[duck];"
          f"[vo][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,"
          f"atrim=0:{total:.3f},aresample={SR}[a];"
          f"[0:v]ass={ass}[v]")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={total:.3f}",
         "-i", vo_t, "-i", music, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-profile:v", "high",
         "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-movflags", "+faststart",
         "-t", f"{total:.3f}", OUT if not fake else os.path.join(BUILD, "test_fake.mp4")])
    print("wrote", OUT if not fake else os.path.join(BUILD, "test_fake.mp4"))


if __name__ == "__main__":
    main()
