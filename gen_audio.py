#!/usr/bin/env python3
"""Generate natural English audio (Microsoft neural TTS via edge-tts) for all
words used in the app, and emit audio.js mapping word -> filename.

Run: python gen_audio.py
"""
import re, os, json, asyncio, edge_tts

VOICE = "en-US-AriaNeural"   # natural US English neural voice
RATE = "-5%"                 # slight slowdown for clearer enunciation
HTML = "index.html"
AUDIO_DIR = "audio"

os.makedirs(AUDIO_DIR, exist_ok=True)

def slug(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())

def extract_words(html):
    words = []
    # WORDS: word:'...'
    words += re.findall(r"word:'([^']+)'", html)
    # IPA_DATA examples arrays: examples:['a','b','c']
    for block in re.findall(r"examples:\[([^\]]+)\]", html):
        words += re.findall(r"'([^']+)'", block)
    # PHONICS_RULES examples strings: examples:'a, b, c'
    for block in re.findall(r"examples:'([^']+)'", html):
        words += [w.strip() for w in block.split(",") if w.strip()]
    # de-dup, keep lowercase keys, preserve original for TTS
    seen, out = set(), []
    for w in words:
        lw = w.lower()
        if lw not in seen and lw:
            seen.add(lw)
            out.append(w)
    return out

async def generate(words):
    mapping, used = {}, {}
    sem = asyncio.Semaphore(8)  # concurrency
    async def one(w):
        async with sem:
            s = slug(w)
            if s in used:
                used[s] += 1
                s = f"{s}_{used[s]}"
            else:
                used[s] = 0
            fname = f"{s}.mp3"
            mapping[w.lower()] = fname
            try:
                comm = edge_tts.Communicate(text=w, voice=VOICE, rate=RATE)
                await comm.save(os.path.join(AUDIO_DIR, fname))
            except Exception as e:
                print("ERR", w, e)
    await asyncio.gather(*[one(w) for w in words])
    return mapping

def main():
    html = open(HTML, encoding="utf-8").read()
    words = extract_words(html)
    print(f"Extracted {len(words)} unique words")
    mapping = asyncio.run(generate(words))
    # emit audio.js
    with open("audio.js", "w", encoding="utf-8") as f:
        f.write("window.WORD_AUDIO = " + json.dumps(mapping, ensure_ascii=False) + ";\n")
    # cleanup test file
    testf = os.path.join(AUDIO_DIR, "_test.mp3")
    if os.path.exists(testf):
        os.remove(testf)
    print(f"Wrote audio.js with {len(mapping)} entries")

if __name__ == "__main__":
    main()
