"""Cuts the fine grain tile out of the source photograph.

    python scripts/make_grain_tooth.py <photograph> [out]

The fine tooth on the page is no longer procedural: it is a 256x256 crop of a photographed
concrete surface, which is where #77 took it. The mottle underneath it is still
`feTurbulence`, so only this one layer has a file behind it.

The source is a free-use stock photograph of a concrete surface, which is all that is known
about where it came from: no licence file sits beside the tile, because Tim says the image
is free to use and there is nothing further to record.

It is 7360x4912, greyscale, and is **not** in the repo — 13.8MB of which the tile keeps a
thousandth. It stays on Tim's disk, and this script is the record of what was done to it, so
the derivation is readable and repeatable without it. Given the same photograph it writes
the same bytes: there is nothing random here and WEBP lossless at method 6 is
deterministic.

**The crop** is (3000, 2000) to (3256, 2256) at native resolution, no resampling. Native
because the tooth is the photograph's own grain and scaling it is the one thing that would
destroy it; that corner of the frame for the plainest reason, that it holds surface and
nothing else — no lit edge, no join, no gradient across it that would read on the page as a
patch rather than as paper.

**Exactly periodic**, because the tile is a `background-image` and its right edge meets its
own left edge every 256px. A raised-cosine blend of the four half-shifted copies: each copy
carries the seam into the middle of a different one, and the weights sum to one everywhere,
so the edges of the result are continuous by construction rather than by retouching. The
usual mirror-and-fold instead would put a visible axis of symmetry every 256px, which at
this size is worse than a seam.

**Then the contrast goes back.** Averaging four copies of the same surface cancels some of
it — the four are decorrelated at this offset, so the blend lands near half the amplitude.
Rescaling to the crop's own standard deviation puts it back, and centring on 127.5 rather
than on the crop's mean keeps the tile neutral, which matters because the page multiplies
and screens through it: a tile whose mean is not 127.5 would tint the blue as well as
texture it.

**Lossless, not lossy.** The whole signal here is a standard deviation of 4.76 out of 255.
WEBP q90 lays an rms error of 1.53 on top of that, a third of the signal, and q100 is 51KB
against lossless at 10.6KB, so lossy is both worse and bigger. Nothing to weigh.

256 rather than 512: measured identical on the rendered page at a third of the weight, and
the autocorrelation at the 256px lag reads the same as at 257 and 320, so what is left is a
smooth trend across the panel and not a repeat anyone can see.

What it writes is 256x256 and 10,610 bytes, rescaled to the crop's own standard deviation
of 4.723, which reads 4.732 once the result is rounded to 8 bits. The script prints all of
them, so a rebuild that does not reproduce the file says so rather than passing quietly.
"""
import sys, pathlib
import numpy as np
from PIL import Image

CROP = (3000, 2000, 3256, 2256)
OUT = pathlib.Path(__file__).resolve().parent.parent / 'grain' / 'tooth-256.webp'

src_path = pathlib.Path(sys.argv[1]).expanduser()
out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else OUT

src = Image.open(src_path).convert('L')
raw = np.asarray(src.crop(CROP)).astype(float)

# exactly periodic: a raised-cosine blend of the four half-shifted copies
h, w = raw.shape
wx = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(w) / w))[None, :]
wy = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(h) / h))[:, None]
A, B = raw, np.roll(raw, w // 2, 1)
C, D = np.roll(raw, h // 2, 0), np.roll(np.roll(raw, h // 2, 0), w // 2, 1)
t = A * wx * wy + B * (1 - wx) * wy + C * wx * (1 - wy) + D * (1 - wx) * (1 - wy)

# the blend costs contrast; put the crop's own back, centred on neutral
t = (t - t.mean()) * (raw.std() / t.std()) + 127.5

tile = np.clip(t, 0, 255).astype('uint8')
out.parent.mkdir(parents=True, exist_ok=True)
Image.fromarray(tile).save(out, 'WEBP', lossless=True, method=6)

print('%s from %s' % (out, src_path))
print('source crop  %dx%d at %s, std %.3f' % (w, h, CROP, raw.std()))
print('tile         %dx%d, std %.3f' % (tile.shape[1], tile.shape[0], tile.std()))
print('encoding     lossless WEBP, %d bytes' % out.stat().st_size)
