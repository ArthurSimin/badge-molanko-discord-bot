from __future__ import annotations

import io
import math
from typing import Optional

from PIL import Image, ImageSequence


def process_gif_to_spritesheet(
    data: bytes,
    cols: int,
    max_width: Optional[int],
    scale: int,
) -> tuple[io.BytesIO, tuple[int, int, int, int, int, int, int]]:
    """Convert an animated image to a PNG spritesheet.

    This function is synchronous by design. Async callers should run it with
    ``asyncio.to_thread`` so Pillow work never blocks the event loop.
    """
    with Image.open(io.BytesIO(data)) as gif:
        if not getattr(gif, "is_animated", False):
            raise ValueError(
                "This image is not animated. Please provide a GIF or other animated format."
            )

        frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(gif)]
        if not frames:
            raise ValueError("No frames could be extracted.")

        first_w, first_h = frames[0].size
        for index, frame in enumerate(frames):
            if frame.size != (first_w, first_h):
                frames[index] = frame.resize((first_w, first_h), Image.NEAREST)

        total_frames = len(frames)

        if cols <= 0:
            if max_width is not None:
                frame_scaled_w = first_w * scale
                cols = max(1, max_width // frame_scaled_w)
                cols = min(cols, total_frames)
            else:
                ideal_cols = math.ceil(math.sqrt(total_frames))
                max_reasonable_cols = max(1, min(8, total_frames))
                cols = max(1, min(ideal_cols, max_reasonable_cols))

        rows = math.ceil(total_frames / cols)

        if scale != 1:
            frame_w = first_w * scale
            frame_h = first_h * scale
            frames = [
                frame.resize((frame_w, frame_h), Image.NEAREST)
                for frame in frames
            ]
        else:
            frame_w, frame_h = first_w, first_h

        spritesheet_w = cols * frame_w
        spritesheet_h = rows * frame_h
        spritesheet = Image.new(
            "RGBA",
            (spritesheet_w, spritesheet_h),
            (0, 0, 0, 0),
        )

        for index, frame in enumerate(frames):
            x = (index % cols) * frame_w
            y = (index // cols) * frame_h
            spritesheet.paste(frame, (x, y), frame)

        output = io.BytesIO()
        spritesheet.save(output, format="PNG")
        output.seek(0)

        return output, (
            total_frames,
            cols,
            rows,
            frame_w,
            frame_h,
            spritesheet_w,
            spritesheet_h,
        )
