"""
Recognition + orbital computation pipeline.

Flow for a single observation:
    1. Load each Photo from MinIO via default_storage.
    2. Run CometDetector (ONNX) → pixel (x, y) per photo.
    3. pixel_to_radec → (RA, Dec) per photo using telescope focal length
       and the sky pointing stored in Observation.coordinates.
    4. compute_orbital_elements → Keplerian elements via scipy.
    5. Persist RecognitionResult and upsert Calculation.

The public entry point is run_pipeline(observation_id).
It is designed to be called either:
  - directly (synchronous, blocks until done), or
  - from a background thread / Celery task (preferred for production).
"""

import io
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from astropy.time import Time
from PIL import Image, ImageDraw

from ..models import Calculation, Observation, RecognitionResult, RecognitionTask
from .orbital import compute_orbital_elements, pixel_to_radec
from .recognition import CometDetector

logger = logging.getLogger(__name__)

_MODEL_PATH = getattr(settings, "ONNX_MODEL_PATH", "models/model.onnx")

# Assumed time gap between consecutive frames in one observation session [seconds].
# Replace with Photo.taken_at once that field is populated by clients.
_FRAME_INTERVAL_S = 60


def run_pipeline(observation_id: int) -> dict | None:
    """
    Execute the recognition + orbital computation pipeline.

    Creates / updates RecognitionTask, RecognitionResult, and Calculation.
    Returns the orbital element dict on success, None on failure.
    Raises ObservationNotFound if the observation does not exist.
    """
    try:
        observation = Observation.objects.select_related("telescope", "comet").get(
            pk=observation_id
        )
    except Observation.DoesNotExist:
        logger.error("Observation %d not found", observation_id)
        raise

    task_id = f"pipeline_{observation_id}_{int(time.time())}"
    task = RecognitionTask.objects.create(
        observation=observation,
        task_id=task_id,
        status="processing",
    )

    try:
        result = _run(observation, task)
        task.status = "completed"
        task.save(update_fields=["status"])
        return result
    except Exception as exc:
        logger.exception("Pipeline failed for observation %d", observation_id)
        task.status = "failed"
        task.save(update_fields=["status"])
        raise exc


# ---------------------------------------------------------------------------

def _run(observation: Observation, task: RecognitionTask) -> dict | None:
    photos = list(observation.photos.all())
    if not photos:
        raise ValueError("No photos attached to observation")

    detector = CometDetector.get(_MODEL_PATH)

    # --- Step 1: ONNX detection on each photo ---
    detections: list[tuple] = []  # (photo, det_dict)
    for photo in photos:
        try:
            with default_storage.open(photo.file_path, "rb") as fh:
                image_bytes = fh.read()
            det = detector.detect(image_bytes)
            if det is not None:
                detections.append((photo, det))
                logger.debug(
                    "Photo %s: comet at (%.1f, %.1f) conf=%.3f",
                    photo.file_name, det["x"], det["y"], det["confidence"],
                )
        except Exception as exc:
            logger.warning("Skipping photo %s: %s", photo.file_name, exc)

    if len(detections) < 3:
        observation.status = 'rejected'
        observation.save(update_fields=['status'])
        logger.warning(
            "Observation %d: only %d comet detection(s) (< 3), auto-rejected",
            observation.id, len(detections),
        )
        return None

    # Draw bounding boxes and save annotated images to MinIO
    all_coords = []
    for p, d in detections:
        recognized_path = None
        try:
            bbox_w = d.get("bbox_w")
            bbox_h = d.get("bbox_h")
            if bbox_w and bbox_h:
                with default_storage.open(p.file_path, "rb") as fh:
                    image_bytes = fh.read()
                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                draw = ImageDraw.Draw(img)
                cx, cy = d["x"], d["y"]
                x0 = cx - bbox_w / 2
                y0 = cy - bbox_h / 2
                x1 = cx + bbox_w / 2
                y1 = cy + bbox_h / 2
                draw.rectangle([x0, y0, x1, y1], outline="#00FF00", width=3)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=90)
                save_path = f"observations/{observation.id}/recognized/{p.file_name}"
                if default_storage.exists(save_path):
                    default_storage.delete(save_path)
                recognized_path = default_storage.save(save_path, ContentFile(buf.getvalue()))
        except Exception as exc:
            logger.warning("Could not annotate photo %s: %s", p.file_name, exc)

        all_coords.append({
            "photo_id": p.id,
            "file_name": p.file_name,
            "x": d["x"],
            "y": d["y"],
            "bbox_w": d.get("bbox_w"),
            "bbox_h": d.get("bbox_h"),
            "confidence": d["confidence"],
            "img_width": d.get("width"),
            "img_height": d.get("height"),
            "recognized_path": recognized_path,
        })
    avg_conf = sum(d["confidence"] for _, d in detections) / len(detections)
    RecognitionResult.objects.update_or_create(
        task=task,
        defaults={"coordinates": all_coords, "confidence": avg_conf},
    )

    # --- Step 2: pixel → RA/Dec astrometry ---
    focal_length_mm = observation.telescope.focal_length or 1000.0
    center_ra, center_dec = _parse_sky_coords(observation.coordinates)

    ra_dec_list: list[tuple[float, float]] = []
    times_jd: list[float] = []

    n = len(detections)
    for idx, (photo, det) in enumerate(detections):
        # Use Photo.taken_at when available; otherwise space frames evenly
        if hasattr(photo, "taken_at") and photo.taken_at is not None:
            t = photo.taken_at
        else:
            offset_s = idx * _FRAME_INTERVAL_S / max(n - 1, 1)
            t = observation.date_obs + timedelta(seconds=offset_s)

        ra, dec = pixel_to_radec(
            det["x"], det["y"],
            det["width"], det["height"],
            center_ra, center_dec,
            focal_length_mm,
        )
        ra_dec_list.append((ra, dec))
        times_jd.append(Time(t).jd)

        logger.debug("  Frame %d: RA=%.4f Dec=%.4f  JD=%.4f", idx, ra, dec, times_jd[-1])

    # --- Step 3: orbit determination ---
    elements = None
    if len(ra_dec_list) >= 3:
        elements = compute_orbital_elements(ra_dec_list, times_jd)

    # --- Step 4: save Calculation ---
    if elements and observation.comet_id:
        Calculation.objects.update_or_create(
            obs=observation,
            defaults={
                "comet": observation.comet,
                "axis": elements["a"],
                "exentricity": elements["e"],
                "inclination": elements["i"],
                "longtitude": elements["node"],
                "arg_perihelion": elements["peri"],
                "orbital_period": elements["period"],
            },
        )
        logger.info(
            "Observation %d: orbit saved — a=%.3f AU, e=%.3f, i=%.2f°, T=%s yr",
            observation.id,
            elements["a"], elements["e"], elements["i"],
            f"{elements['period']:.2f}" if elements["period"] else "—",
        )
    else:
        logger.warning("Observation %d: orbit determination returned no result", observation.id)

    return elements


def _parse_sky_coords(coords_str: str) -> tuple[float, float]:
    """
    Parse 'ra_deg,dec_deg' or 'ra_deg dec_deg' string.
    Returns (ra_deg, dec_deg). Defaults to (0.0, 0.0) on parse error.
    """
    try:
        parts = coords_str.replace(" ", ",").split(",")
        return float(parts[0]), float(parts[1])
    except Exception:
        logger.warning("Cannot parse sky coordinates %r; using (0, 0)", coords_str)
        return 0.0, 0.0
