#!/usr/bin/env python3
"""Build phoneme_audio.js: real isolated IPA phoneme recordings for the 44
English phonemes used by the app.

Strategy:
  - The cached Wikipedia IPA chart HTML files (/tmp/consonants.html,
    /tmp/vowels.html) pair each chart symbol with its Commons audio file
    (the PhonosButton `file` attribute, e.g. "Voiceless bilabial plosive.ogg").
  - We map each APP phoneme symbol -> the matching CHART symbol, look up the
    Commons file name, convert spaces->underscores, compute the MD5-based
    upload URL, download the OGG and convert to MP3.
  - Diphthongs have no isolated recording -> skipped (app falls back to the
    pre-generated keyword word audio).

Note: the chart uses cardinal/base vowels for the long-vowel symbols
(e.g. /iː/ -> chart "i" = Close front unrounded vowel), the script-g "ɡ"
for the velar plosive, and "t̠ʃ"/"d̠ʒ" for the affricates.
"""
import re
import json
import hashlib
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "phoneme_audio")

# app symbol (exact unicode from index.html IPA_DATA) -> chart symbol in master map
# (None means diphthong: no isolated recording, fall back to keyword audio)
APP_TO_CHART = {
    # short vowels
    "\u026A": "ɪ", "e": "e", "\u00E6": "æ", "\u028C": "ʌ", "\u028A": "ʊ", "\u0259": "ə",
    # long vowels (chart uses base cardinal vowels)
    "i\u02D0": "i", "\u0251\u02D0": "\u0251", "\u0254\u02D0": "\u0254",
    "u\u02D0": "u", "\u025C\u02D0": "\u025C",
    # diphthongs -> no isolated recording
    "e\u026A": None, "a\u026A": None, "\u0254\u026A": None, "a\u028A": None,
    "\u0259\u028A": None, "\u026A\u0259": None, "e\u0259": None, "\u028A\u0259": None,
    # plosives
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "\u0261": "ɡ",
    # fricatives
    "f": "f", "v": "v", "\u03B8": "θ", "\u00F0": "ð", "s": "s", "z": "z",
    "\u0283": "ʃ", "\u0292": "ʒ", "h": "h",
    # affricates (chart uses t̠ʃ / d̠ʒ)
    "t\u0283": "t̠ʃ", "d\u0292": "d̠ʒ",
    # nasals
    "m": "m", "n": "n", "\u014B": "ŋ",
    # approximants
    "l": "l", "r": "r", "j": "j", "w": "w",
}

# ascii output filename for each app symbol (mp3)
OUT_NAME = {
    "\u026A": "i_short", "e": "e_short", "\u00E6": "ae", "\u028C": "uh", "\u028A": "u_short", "\u0259": "schwa",
    "i\u02D0": "ee", "\u0251\u02D0": "ar", "\u0254\u02D0": "or", "u\u02D0": "oo", "\u025C\u02D0": "er_open",
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "\u0261": "g",
    "f": "f", "v": "v", "\u03B8": "th_voiceless", "\u00F0": "th_voiced", "s": "s", "z": "z",
    "\u0283": "sh", "\u0292": "zh", "h": "h",
    "t\u0283": "ch", "d\u0292": "j",
    "m": "m", "n": "n", "\u014B": "ng",
    "l": "l", "r": "r", "j": "y", "w": "w",
}

# For English /r/ the alveolar approximant is more accurate than the trill.
# Map app "r" directly to that Commons file (override chart lookup).
DIRECT_FILE = {
    "r": "Alveolar approximant.ogg",
}


def parse_html(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    cells = re.split(r'<div class="IPA-audiocell">', html)[1:]
    result = {}
    for cell in cells:
        sym_m = re.search(r'IPA-audiocell-symbol".*?<a [^>]*>([^<]+)</a>', cell, re.S)
        file_m = re.search(r'"file":"([^"]+\.(?:ogg|oga))"', cell)
        if not sym_m or not file_m:
            continue
        sym = sym_m.group(1).strip()
        fname = file_m.group(1).strip()
        result[sym] = fname
    return result


def commons_url(filename):
    # canonical Commons filename uses underscores; MD5-based path
    canon = filename.replace(" ", "_")
    md5 = hashlib.md5(canon.encode("utf-8")).hexdigest()
    return f"https://upload.wikimedia.org/wikipedia/commons/{md5[0]}/{md5[:2]}/{canon}"


def download_convert(url, mp3):
    tmp = mp3 + ".tmp"
    # retry on rate-limit (429) with backoff
    for attempt in range(5):
        try:
            r = subprocess.run(["curl", "-fsSL", url, "-o", tmp],
                               capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.getsize(tmp) > 500:
                break
            if os.path.exists(tmp):
                os.remove(tmp)
            # 429 -> back off and retry
            time.sleep(6 + attempt * 4)
        except Exception:
            time.sleep(3 + attempt * 3)
    else:
        return False
    try:
        subprocess.run(["ffmpeg", "-y", "-i", tmp, "-ac", "1", "-ar", "22050", mp3],
                       check=True, capture_output=True, timeout=60)
    except subprocess.CalledProcessError:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    if os.path.exists(tmp):
        os.remove(tmp)
    return True


def main():
    cons = parse_html("/tmp/consonants.html")
    vows = parse_html("/tmp/vowels.html")
    master = {}
    master.update(vows)
    master.update(cons)

    os.makedirs(OUT_DIR, exist_ok=True)
    mapping = {}
    for sym, chart in APP_TO_CHART.items():
        if chart is None:
            print(f"SKIP (diphthong, no isolated rec) {sym}")
            continue
        out = OUT_NAME[sym]
        if sym in DIRECT_FILE:
            fname = DIRECT_FILE[sym]
        else:
            if chart not in master:
                print(f"  !! MISSING chart symbol for {sym} ({chart!r})")
                continue
            fname = master[chart]
        url = commons_url(fname)
        mp3 = os.path.join(OUT_DIR, out + ".mp3")
        # skip if already downloaded
        if os.path.exists(mp3) and os.path.getsize(mp3) > 1000:
            mapping[sym] = out + ".mp3"
            print(f"OK* {sym} -> {fname} (cached)")
            continue
        ok = download_convert(url, mp3)
        if ok:
            mapping[sym] = out + ".mp3"
            print(f"OK  {sym} -> {fname} -> {out}.mp3")
        else:
            print(f"FAIL {sym} -> {fname} [{url}]")
        time.sleep(2.5)

    with open(os.path.join(ROOT, "phoneme_audio.js"), "w", encoding="utf-8") as f:
        f.write("window.PHONEME_AUDIO = ")
        json.dump(mapping, f, ensure_ascii=False, indent=2)
        f.write(";\n")
    print(f"\nWrote phoneme_audio.js with {len(mapping)} entries")
    return mapping


if __name__ == "__main__":
    main()
