import argparse
import io
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imgconvrtr import convert_img_format


PROFILE_CONFIGS = {
    "balanced": {
        "jpeg": {"quality": 88, "lossless": False, "advanced_options": {"jpeg_progressive": True, "jpeg_subsampling": "4:2:0"}},
        "webp": {"quality": 82, "lossless": False, "advanced_options": {"webp_method": 4, "webp_alpha_quality": 90, "webp_exact": False}},
        "avif": {"quality": 75, "lossless": False, "advanced_options": {"avif_speed": 6, "avif_subsampling": "4:2:0"}},
    },
    "high_quality": {
        "jpeg": {"quality": 92, "lossless": False, "advanced_options": {"jpeg_progressive": True, "jpeg_subsampling": "4:4:4"}},
        "webp": {"quality": 90, "lossless": False, "advanced_options": {"webp_method": 6, "webp_alpha_quality": 100, "webp_exact": True}},
        "avif": {"quality": 80, "lossless": False, "advanced_options": {"avif_speed": 4, "avif_subsampling": "4:4:4"}},
    },
}

DEFAULT_THRESHOLDS = {
    "natural_gradient": {"jpeg": {"psnr_db": 30.0, "ssim": 0.95}, "webp": {"psnr_db": 30.0, "ssim": 0.95}, "avif": {"psnr_db": 30.0, "ssim": 0.95}},
    "graphics_text": {"jpeg": {"psnr_db": 30.0, "ssim": 0.95}, "webp": {"psnr_db": 30.0, "ssim": 0.95}, "avif": {"psnr_db": 30.0, "ssim": 0.95}},
    # JPEG is intentionally excluded for alpha_overlay because alpha->JPEG flattening is lossy by definition.
    "alpha_overlay": {"webp": {"psnr_db": 20.0, "ssim": 0.90}, "avif": {"psnr_db": 25.0, "ssim": 0.95}},
}


def to_rgb_array(img):
    return np.asarray(img.convert("RGB"), dtype=np.float32)


def compute_psnr(original_rgb, converted_rgb):
    mse = np.mean((original_rgb - converted_rgb) ** 2)
    if mse <= 1e-10:
        return float("inf")
    return float(20 * np.log10(255.0 / np.sqrt(mse)))


def compute_ssim(original_rgb, converted_rgb):
    # Global SSIM estimate across channels; lightweight and dependency-free.
    x = original_rgb
    y = converted_rgb
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_x = np.mean(x)
    mu_y = np.mean(y)
    sigma_x = np.var(x)
    sigma_y = np.var(y)
    covariance = np.mean((x - mu_x) * (y - mu_y))
    numerator = (2 * mu_x * mu_y + c1) * (2 * covariance + c2)
    denominator = (mu_x ** 2 + mu_y ** 2 + c1) * (sigma_x + sigma_y + c2)
    if denominator == 0:
        return 1.0
    return float(numerator / denominator)


def generate_fixtures():
    fixtures = {}

    # Natural-like gradient with gentle texture.
    w, h = 512, 384
    gx = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    gy = np.tile(np.linspace(255, 0, h, dtype=np.uint8).reshape(h, 1), (1, w))
    rng = np.random.default_rng(42)
    noise = rng.integers(0, 16, size=(h, w), dtype=np.uint8)
    mixed = ((gx.astype(np.uint16) // 2) + (gy.astype(np.uint16) // 3) + noise.astype(np.uint16)) % 256
    natural = np.stack([gx, gy, mixed.astype(np.uint8)], axis=-1)
    fixtures["natural_gradient"] = Image.fromarray(natural, mode="RGB")

    # Graphics/text-like sharp edges.
    graphics = Image.new("RGB", (512, 384), (245, 245, 245))
    draw = ImageDraw.Draw(graphics)
    draw.rectangle((20, 20, 220, 160), fill=(10, 130, 255))
    draw.rectangle((260, 20, 500, 160), fill=(255, 90, 40))
    draw.line((20, 210, 500, 210), fill=(20, 20, 20), width=3)
    draw.text((30, 240), "IMGCONVERTER QUALITY TEST", fill=(15, 15, 15))
    draw.text((30, 285), "4:4:4 should preserve text edges", fill=(40, 40, 40))
    fixtures["graphics_text"] = graphics

    # Transparency-heavy fixture for WebP behavior.
    alpha = Image.new("RGBA", (384, 384), (0, 0, 0, 0))
    adraw = ImageDraw.Draw(alpha)
    adraw.ellipse((30, 30, 350, 350), fill=(255, 30, 30, 180))
    adraw.rectangle((80, 80, 300, 300), fill=(20, 140, 255, 120))
    adraw.text((85, 170), "ALPHA", fill=(255, 255, 255, 220))
    fixtures["alpha_overlay"] = alpha

    return fixtures


def convert_fixture(img, target_format, cfg):
    source = io.BytesIO()
    source_format = "PNG" if img.mode == "RGBA" else "JPEG"
    save_kwargs = {"format": source_format}
    if source_format == "JPEG":
        save_kwargs["quality"] = 95
    img.save(source, **save_kwargs)
    source_bytes = source.getvalue()

    t0 = time.perf_counter()
    try:
        converted = convert_img_format(
            source_bytes,
            target_format,
            quality=cfg["quality"],
            lossless=cfg["lossless"],
            optimize=False,
            preserve_icc=True,
            preserve_exif=False,
            preserve_xmp=False,
            advanced_options=cfg.get("advanced_options", {}),
        )
    except Exception as exc:
        raise RuntimeError(f"Conversion failed for target={target_format}: {exc}") from exc
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    converted_bytes = converted.getvalue()
    if not converted_bytes:
        raise RuntimeError(f"Conversion produced empty output for target={target_format}")

    try:
        with Image.open(io.BytesIO(converted_bytes)) as roundtrip:
            roundtrip.load()
            converted_img = roundtrip.copy()
    except Exception as exc:
        raise RuntimeError(f"Round-trip decode failed for target={target_format}: {exc}") from exc

    original_rgb = to_rgb_array(img)
    converted_rgb = to_rgb_array(converted_img.resize(img.size, Image.Resampling.LANCZOS))
    psnr = compute_psnr(original_rgb, converted_rgb)
    ssim = compute_ssim(original_rgb, converted_rgb)
    if math.isnan(psnr) or math.isnan(ssim):
        raise RuntimeError(f"Metric computation failed for target={target_format} (NaN encountered)")

    return {
        "source_size_bytes": len(source_bytes),
        "output_size_bytes": len(converted_bytes),
        "size_ratio": (len(converted_bytes) / len(source_bytes)) if source_bytes else None,
        "encode_time_ms": elapsed_ms,
        "psnr_db": psnr,
        "ssim": ssim,
    }


def run_suite(profile):
    fixtures = generate_fixtures()
    targets = ["jpeg", "webp", "avif"]
    results = {"profile": profile, "fixtures": {}}

    for fixture_name, fixture_img in fixtures.items():
        fixture_results = {}
        for target in targets:
            cfg = PROFILE_CONFIGS[profile][target]
            try:
                fixture_results[target] = convert_fixture(fixture_img, target, cfg)
            except Exception as exc:
                fixture_results[target] = {"error": str(exc), "error_type": type(exc).__name__}
        results["fixtures"][fixture_name] = fixture_results

    return results


def print_summary(results):
    print(f"Profile: {results['profile']}")
    for fixture_name, formats in results["fixtures"].items():
        print(f"\nFixture: {fixture_name}")
        for fmt, values in formats.items():
            if "error" in values:
                print(f"  {fmt.upper()}: ERROR - {values['error']}")
                continue
            print(
                f"  {fmt.upper()}: "
                f"time={values['encode_time_ms']:.1f}ms "
                f"size={values['output_size_bytes']}B "
                f"ratio={values['size_ratio']:.2f} "
                f"PSNR={values['psnr_db']:.2f} "
                f"SSIM={values['ssim']:.4f}"
            )


def load_thresholds(path):
    if path is None:
        return DEFAULT_THRESHOLDS
    if not path.exists():
        raise FileNotFoundError(f"Threshold file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Could not parse threshold file '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Threshold file must contain a JSON object at top level: {path}")
    return data


def evaluate_regressions(results, thresholds):
    failures = []
    for fixture_name, format_thresholds in thresholds.items():
        fixture_results = results["fixtures"].get(fixture_name)
        if fixture_results is None:
            failures.append(f"Missing fixture in results: {fixture_name}")
            continue
        for fmt, metric_thresholds in format_thresholds.items():
            values = fixture_results.get(fmt)
            if values is None:
                failures.append(f"Missing format result: fixture={fixture_name}, format={fmt}")
                continue
            if "error" in values:
                failures.append(f"Conversion error: fixture={fixture_name}, format={fmt}, error={values['error']}")
                continue
            for metric_name, min_expected in metric_thresholds.items():
                if metric_name not in values:
                    failures.append(f"Missing metric '{metric_name}' for fixture={fixture_name}, format={fmt}")
                    continue
                actual = values[metric_name]
                if actual < min_expected:
                    failures.append(
                        f"Threshold fail: fixture={fixture_name}, format={fmt}, metric={metric_name}, "
                        f"actual={actual:.4f}, min_expected={min_expected:.4f}"
                    )
    return failures


def main():
    parser = argparse.ArgumentParser(description="Run image quality regression checks for default profiles.")
    parser.add_argument("--profile", choices=PROFILE_CONFIGS.keys(), default="balanced")
    parser.add_argument("--json-out", type=Path, default=Path("tests/quality_regression_latest.json"))
    parser.add_argument("--thresholds", type=Path, default=None, help="Optional JSON file with metric thresholds.")
    parser.add_argument("--enforce-thresholds", action="store_true", help="Exit non-zero when quality thresholds fail.")
    parser.add_argument("--fail-on-errors", action="store_true", help="Exit non-zero if any conversion case returns an error.")
    args = parser.parse_args()

    try:
        results = run_suite(args.profile)
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print_summary(results)
        print(f"\nSaved JSON results to: {args.json_out}")
    except Exception as exc:
        print(f"FATAL: Failed to execute quality regression suite: {exc}", file=sys.stderr)
        sys.exit(2)

    conversion_errors = []
    for fixture_name, formats in results["fixtures"].items():
        for fmt, values in formats.items():
            if "error" in values:
                conversion_errors.append(f"Conversion error: fixture={fixture_name}, format={fmt}, error={values['error']}")

    if conversion_errors:
        print("\nConversion errors detected:")
        for item in conversion_errors:
            print(f"- {item}")
        if args.fail_on_errors:
            print("\nExiting with failure due to --fail-on-errors.")
            sys.exit(1)

    if args.enforce_thresholds:
        try:
            thresholds = load_thresholds(args.thresholds)
        except Exception as exc:
            print(f"FATAL: Threshold loading failed: {exc}", file=sys.stderr)
            sys.exit(2)
        failures = evaluate_regressions(results, thresholds)
        if failures:
            print("\nQuality threshold failures:")
            for failure in failures:
                print(f"- {failure}")
            sys.exit(1)
        print("\nAll enforced thresholds passed.")


if __name__ == "__main__":
    main()
