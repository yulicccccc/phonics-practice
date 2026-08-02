#!/usr/bin/env python3
import hashlib, os, subprocess, time, json

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "phoneme_audio")

# (app_symbol, commons_filename_with_spaces, out_ascii)
TARGETS = [
    ("k", "Voiceless velar plosive.ogg", "k"),
    ("l", "Alveolar lateral approximant.ogg", "l"),
]

def url(fn):
    canon = fn.replace(" ", "_")
    md5 = hashlib.md5(canon.encode()).hexdigest()
    return f"https://upload.wikimedia.org/wikipedia/commons/{md5[0]}/{md5[:2]}/{canon}"

def dl(u, mp3):
    tmp = mp3 + ".tmp"
    for a in range(6):
        try:
            r = subprocess.run(["curl", "-fsSL", u, "-o", tmp], capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.getsize(tmp) > 500:
                break
            if os.path.exists(tmp): os.remove(tmp)
            time.sleep(8 + a * 5)
        except Exception:
            time.sleep(8 + a * 5)
    else:
        return False
    try:
        subprocess.run(["ffmpeg", "-y", "-i", tmp, "-ac", "1", "-ar", "22050", mp3],
                       check=True, capture_output=True, timeout=60)
    except subprocess.CalledProcessError:
        if os.path.exists(tmp): os.remove(tmp)
        return False
    if os.path.exists(tmp): os.remove(tmp)
    return True

def main():
    # load existing map
    mp = {}
    pj = os.path.join(ROOT, "phoneme_audio.js")
    if os.path.exists(pj):
        src = open(pj, encoding="utf-8").read()
        # strip "window.PHONEME_AUDIO = " and trailing ";"
        j = src.replace("window.PHONEME_AUDIO =", "").rstrip().rstrip(";")
        mp = json.loads(j)
    for sym, fn, out in TARGETS:
        mp3 = os.path.join(OUT, out + ".mp3")
        if os.path.exists(mp3) and os.path.getsize(mp3) > 1000:
            mp[sym] = out + ".mp3"
            print(f"OK* {sym} (cached)"); continue
        ok = dl(url(fn), mp3)
        if ok:
            mp[sym] = out + ".mp3"
            print(f"OK  {sym} -> {fn}")
        else:
            print(f"FAIL {sym} -> {fn}")
        time.sleep(4)
    with open(pj, "w", encoding="utf-8") as f:
        f.write("window.PHONEME_AUDIO = ")
        json.dump(mp, f, ensure_ascii=False, indent=2)
        f.write(";\n")
    print(f"map now has {len(mp)} entries")

if __name__ == "__main__":
    main()
