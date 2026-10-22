"""Streams a raw 16 kHz Int16 PCM file to the server in real time and prints results.
Usage: python tests/stream_demo.py file.pcm [language]"""
import asyncio, json, sys, websockets

async def main(path, lang="auto", base="ws://localhost:8000"):
    pcm = open(path, "rb").read() + b"\x00" * 32000 * 2  # 2 s trailing silence
    async with websockets.connect(f"{base}/ws/transcribe?language={lang}") as ws:
        async def recv():
            async for m in ws:
                print(json.loads(m))
        r = asyncio.create_task(recv())
        step = 3200  # 100 ms
        for i in range(0, len(pcm), step):
            await ws.send(pcm[i:i + step]); await asyncio.sleep(0.1)
        await ws.send("stop")
        await r

asyncio.run(main(*sys.argv[1:]))
