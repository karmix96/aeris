from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from PIL import Image


def find_plot_frames(
    dataset_root: Path,
    plot_relpath: str = "plots/planform.png",
) -> list[Path]:
    """
    Find plot PNGs under:
        <dataset_root>/geometry/geom_xxxxx/plots/planform.png
    """
    geometry_dir = dataset_root / "geometry"
    if not geometry_dir.exists():
        raise FileNotFoundError(f"Geometry directory not found: {geometry_dir}")

    frames: list[Path] = []
    for geom_dir in sorted(p for p in geometry_dir.iterdir() if p.is_dir()):
        candidate = geom_dir / plot_relpath
        if candidate.exists():
            frames.append(candidate)

    return frames


def load_frames(
    frame_paths: Iterable[Path],
    *,
    resize_width: int | None = None,
    resize_height: int | None = None,
) -> list[Image.Image]:
    """
    Load frames as RGB images.
    Optionally resize all frames to a common size.
    """
    images: list[Image.Image] = []

    for path in frame_paths:
        with Image.open(path) as img:
            frame = img.convert("RGB")

            if resize_width is not None and resize_height is not None:
                frame = frame.resize((resize_width, resize_height))

            images.append(frame)

    return images


def infer_common_size(frame_paths: list[Path]) -> tuple[int, int]:
    """
    Use the size of the first frame as the common output size.
    """
    if not frame_paths:
        raise ValueError("No frame paths provided.")

    with Image.open(frame_paths[0]) as img:
        return img.size


def make_gif(
    dataset_root: Path,
    output_path: Path,
    *,
    duration_ms: int = 200,
    loop: int = 0,
    max_frames: int | None = None,
    every_n: int = 1,
    resize_to_first: bool = True,
) -> None:
    frame_paths = find_plot_frames(dataset_root)

    if every_n < 1:
        raise ValueError("every_n must be >= 1")

    if every_n > 1:
        frame_paths = frame_paths[::every_n]

    if max_frames is not None:
        frame_paths = frame_paths[:max_frames]

    if not frame_paths:
        raise FileNotFoundError(
            f"No plot frames found under: {dataset_root / 'geometry'}"
        )

    resize_width = None
    resize_height = None
    if resize_to_first:
        resize_width, resize_height = infer_common_size(frame_paths)

    frames = load_frames(
        frame_paths,
        resize_width=resize_width,
        resize_height=resize_height,
    )

    if not frames:
        raise RuntimeError("No frames were loaded for GIF creation.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    first, *rest = frames
    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        duration=duration_ms,
        loop=loop,
        optimize=False,
    )

    print(f"GIF created: {output_path}")
    print(f"Frames used: {len(frames)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an animated GIF from AERIS dataset plot frames."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to dataset root, e.g. data/datasets/bwb_dataset_v1_plots",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output GIF path, e.g. outputs/bwb_dataset_v1_plots.gif",
    )
    parser.add_argument(
        "--duration-ms",
        type=int,
        default=200,
        help="Frame duration in milliseconds.",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        help="GIF loop count. 0 means infinite loop.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Maximum number of frames to include.",
    )
    parser.add_argument(
        "--every-n",
        type=int,
        default=1,
        help="Use every Nth frame. Example: 2 keeps every second frame.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    make_gif(
        dataset_root=args.dataset.expanduser().resolve(),
        output_path=args.output.expanduser().resolve(),
        duration_ms=args.duration_ms,
        loop=args.loop,
        max_frames=args.max_frames,
        every_n=args.every_n,
    )


if __name__ == "__main__":
    main()