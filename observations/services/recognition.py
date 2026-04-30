import io
import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

INPUT_SIZE = 640
CONF_THRESHOLD = 0.25


class CometDetector:
    """
    Singleton wrapper around an ONNX YOLOv8 model for comet detection.
    Call CometDetector.get(model_path) to obtain the shared instance.
    """

    _instance = None

    def __init__(self, model_path: str):
        import onnxruntime as ort
        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        logger.info("CometDetector loaded: %s", model_path)

    @classmethod
    def get(cls, model_path: str) -> "CometDetector":
        if cls._instance is None:
            cls._instance = cls(model_path)
        return cls._instance

    def detect(self, image_bytes: bytes) -> dict | None:
        """
        Run inference on raw image bytes.

        Returns a dict with keys:
            x, y          — comet centre in original pixel coordinates
            confidence    — detection confidence [0, 1]
            width, height — original image dimensions
        or None if no detection above threshold.
        """
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_w, orig_h = img.size

        inp = self._preprocess(img)
        outputs = self.session.run(None, {self.input_name: inp})
        return self._best_detection(outputs[0], orig_w, orig_h)

    # ------------------------------------------------------------------

    def _preprocess(self, img: Image.Image) -> np.ndarray:
        resized = img.resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR)
        arr = np.array(resized, dtype=np.float32) / 255.0
        return arr.transpose(2, 0, 1)[np.newaxis]  # (1, 3, H, W)

    def _best_detection(self, output: np.ndarray, orig_w: int, orig_h: int) -> dict | None:
        """
        Parse YOLOv8 output tensor and return the highest-confidence detection.

        YOLOv8 exports in two common shapes:
          (1, 4+nc, N)  — channels-first (need transpose)
          (1, N, 4+nc)  — channels-last  (already usable row-wise)
        where the first 4 values are [cx, cy, w, h] normalised to INPUT_SIZE,
        followed by per-class scores.
        """
        out = output[0]  # drop batch dim
        if out.ndim == 2 and out.shape[0] < out.shape[1]:
            out = out.T  # → (N, 4+nc)

        best_conf = CONF_THRESHOLD
        best = None
        for row in out:
            cx, cy = float(row[0]), float(row[1])
            conf = float(np.max(row[4:])) if row.shape[0] > 5 else float(row[4])
            if conf > best_conf:
                best_conf = conf
                best = {
                    "x": cx / INPUT_SIZE * orig_w,
                    "y": cy / INPUT_SIZE * orig_h,
                    "confidence": conf,
                    "width": orig_w,
                    "height": orig_h,
                }
        return best
