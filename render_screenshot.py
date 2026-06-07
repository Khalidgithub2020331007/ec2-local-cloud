#!/usr/bin/env python3
"""Render CLI output as a professional terminal-style PNG screenshot."""

import sys
import os
from PIL import Image, ImageDraw, ImageFont

FONT_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
    '/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf',
]

# Catppuccin Mocha palette
BG      = (30, 30, 46)
HEADER  = (17, 17, 27)
TEXT    = (205, 214, 244)
DIM     = (166, 173, 200)
PROMPT  = (166, 227, 161)
TITLE_C = (180, 190, 254)
BTN_R   = (243, 139, 168)
BTN_Y   = (249, 226, 175)
BTN_G   = (166, 227, 161)
SSH_HDR = (137, 220, 235)   # cyan — used for SSH-style banners

def get_font(size=14):
    for path in FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def char_width(font, sample="A"):
    """Return approximate character width from font metrics."""
    bbox = font.getbbox(sample)
    return bbox[2] - bbox[0]

def render(title, prompt_cmd, output_text, out_path,
           width=1200, ssh_banner=None, extra_prompt=None):
    """
    title       — window title bar text
    prompt_cmd  — command shown after the $ prompt
    output_text — multi-line output of the command
    out_path    — save destination (PNG)
    ssh_banner  — optional header line shown above the prompt in cyan
    extra_prompt— optional second command shown after output (for multi-cmd shots)
    """
    font = get_font(14)
    PADDING  = 22
    LINE_H   = 20
    HEADER_H = 34

    lines = output_text.rstrip('\n').split('\n') if output_text else []

    # Count rendered lines
    n_lines = len(lines) + 1          # +1 for the command
    if ssh_banner:
        n_lines += len(ssh_banner.split('\n'))
    if extra_prompt:
        n_lines += 1 + len(extra_prompt.get('output', '').split('\n'))

    height = HEADER_H + PADDING + n_lines * LINE_H + PADDING + 6
    height = max(height, 180)

    img  = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(img)

    # ── header bar ───────────────────────────────────────────────────
    draw.rectangle([(0, 0), (width, HEADER_H)], fill=HEADER)
    for i, c in enumerate([BTN_R, BTN_Y, BTN_G]):
        cx, cy = 18 + i * 22, HEADER_H // 2
        draw.ellipse([(cx-7, cy-7), (cx+7, cy+7)], fill=c)
    draw.text((75, 9), title, font=font, fill=TITLE_C)

    y = HEADER_H + PADDING

    # ── optional SSH banner ──────────────────────────────────────────
    if ssh_banner:
        for bl in ssh_banner.split('\n'):
            draw.text((PADDING, y), bl, font=font, fill=SSH_HDR)
            y += LINE_H
        y += 4

    # ── command prompt ───────────────────────────────────────────────
    cw = char_width(font)
    draw.text((PADDING, y), '$ ', font=font, fill=PROMPT)
    draw.text((PADDING + cw * 2, y), prompt_cmd, font=font, fill=TEXT)
    y += LINE_H

    # ── output lines ─────────────────────────────────────────────────
    max_chars = (width - PADDING * 2) // max(cw, 1)
    for line in lines:
        if len(line) > max_chars:
            line = line[:max_chars - 3] + '...'
        draw.text((PADDING, y), line, font=font, fill=DIM)
        y += LINE_H

    # ── optional second command block ────────────────────────────────
    if extra_prompt:
        y += 4
        draw.text((PADDING, y), '$ ', font=font, fill=PROMPT)
        draw.text((PADDING + cw * 2, y), extra_prompt['cmd'], font=font, fill=TEXT)
        y += LINE_H
        for line in extra_prompt.get('output', '').rstrip('\n').split('\n'):
            if len(line) > max_chars:
                line = line[:max_chars - 3] + '...'
            draw.text((PADDING, y), line, font=font, fill=DIM)
            y += LINE_H

    img.save(out_path, 'PNG', optimize=True)
    print(f'  saved → {os.path.basename(out_path)}')


if __name__ == '__main__':
    # CLI usage: render_screenshot.py <title> <cmd> <output_file> < output_text
    if len(sys.argv) < 4:
        print("Usage: render_screenshot.py <title> <cmd> <output_file>", file=sys.stderr)
        sys.exit(1)
    title, cmd, out = sys.argv[1], sys.argv[2], sys.argv[3]
    text = sys.stdin.read()
    render(title, cmd, text, out)
