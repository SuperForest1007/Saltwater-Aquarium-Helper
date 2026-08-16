# -*- coding: utf-8 -*-
"""生成 ReefPal 应用图标：深海蓝渐变 + 白色鱼形 + 气泡。"""
from PIL import Image, ImageDraw
import math, os

SIZES = {"icon-192.png": 192, "icon-512.png": 512, "apple-touch-icon.png": 180}

def draw_icon(size):
    img = Image.new("RGBA", (size, size))
    px = img.load()
    # 深海蓝渐变：上深下浅（#075089 -> #0d8dc4 -> #38b2e0）
    top = (7, 80, 137)
    mid = (13, 141, 196)
    bot = (56, 178, 224)
    for y in range(size):
        t = y / size
        if t < 0.55:
            f = t / 0.55
            c = tuple(int(top[i] + (mid[i] - top[i]) * f) for i in range(3))
        else:
            f = (t - 0.55) / 0.45
            c = tuple(int(mid[i] + (bot[i] - mid[i]) * f) for i in range(3))
        for x in range(size):
            px[x, y] = c + (255,)

    d = ImageDraw.Draw(img)
    s = size / 512.0  # 缩放系数

    # 白色波浪（底部两条）
    for wave_i, amp in enumerate([0.06, 0.10]):
        base = size * (0.80 + wave_i * 0.09)
        points = []
        steps = 72
        for i in range(steps + 1):
            x = i / steps * size
            y = base + math.sin(i / steps * math.pi * 2 * 2) * size * amp
            points.append((x, y))
        points += [(size, size), (0, size)]
        d.polygon(points, fill=(255, 255, 255, 40))

    # 鱼身（白色椭圆，偏左下，适中大小）
    cx, cy = size * 0.46, size * 0.44
    bw, bh = size * 0.28, size * 0.18
    d.ellipse([cx - bw, cy - bh, cx + bw, cy + bh], fill=(255, 255, 255, 255))
    # 鱼尾（三角，右侧）
    tx = cx + bw
    d.polygon([(tx, cy), (tx + size * 0.12, cy - size * 0.13), (tx + size * 0.12, cy + size * 0.13)],
              fill=(255, 255, 255, 255))
    # 背鳍
    d.polygon([(cx - size * 0.05, cy - bh * 0.9), (cx + size * 0.08, cy - bh * 1.5), (cx + size * 0.16, cy - bh * 0.8)],
              fill=(255, 255, 255, 230))
    # 眼睛（深海蓝圆点）
    r = size * 0.028
    d.ellipse([cx + size * 0.08 - r, cy - bh * 0.35 - r, cx + size * 0.08 + r, cy - bh * 0.35 + r],
              fill=(10, 110, 168, 255))
    # 气泡（右上角两个）
    d.ellipse([size * 0.68 - size * 0.03, size * 0.24 - size * 0.03, size * 0.68 + size * 0.03, size * 0.24 + size * 0.03],
              outline=(255, 255, 255, 200), width=max(2, int(size * 0.008)))
    d.ellipse([size * 0.78 - size * 0.02, size * 0.14 - size * 0.02, size * 0.78 + size * 0.02, size * 0.14 + size * 0.02],
              outline=(255, 255, 255, 180), width=max(2, int(size * 0.007)))
    return img

out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
os.makedirs(out_dir, exist_ok=True)
for name, size in SIZES.items():
    img = draw_icon(size)
    img.save(os.path.join(out_dir, name))
    print("生成:", name, size, "x", size)
