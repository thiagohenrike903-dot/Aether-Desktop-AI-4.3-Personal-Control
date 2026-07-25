"""Computer vision subsystem.

Capabilities:
  - face detection + recognition
  - hand landmark detection
  - body / pose estimation
  - OCR (text reading)
  - QR / barcode detection
  - object detection (COCO labels via OpenCV DNN)
  - scene description (a textual summary of what's on frame)

The input is always a base64-encoded JPEG (sent by the frontend over WS
or as multipart upload). The output is a JSON-friendly dict.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import io
import logging
import time
import unicodedata
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .config import settings

log = logging.getLogger("jarvis.vision")


# Lazy module-level handles so we don't pay the cost of loading the models
# until the first frame.
_state: dict[str, Any] = {}
_MAX_FRAME_BASE64_CHARS = 20 * 1024 * 1024
_MAX_FRAME_BYTES = 15 * 1024 * 1024
_MAX_IMAGE_PIXELS = 24_000_000


def _decode(b64_jpeg: str) -> np.ndarray:
    encoded = str(b64_jpeg or "").split(",", 1)[-1].strip()
    if not encoded or len(encoded) > _MAX_FRAME_BASE64_CHARS:
        raise ValueError("Frame vazio ou maior que o limite permitido.")
    try:
        raw = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Frame base64 inválido.") from exc
    if len(raw) > _MAX_FRAME_BYTES:
        raise ValueError("A imagem excede o limite de 15 MB.")
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Não foi possível decodificar a imagem.")
    if int(img.shape[0]) * int(img.shape[1]) > _MAX_IMAGE_PIXELS:
        raise ValueError("A resolução da imagem é grande demais.")
    return img


# --------------------------------------------------------------------------- #
# Model loaders (lazy, cached)
# --------------------------------------------------------------------------- #

def _mediapipe():
    if "mp" not in _state:
        import mediapipe as mp  # type: ignore
        _state["mp"] = mp
    return _state["mp"]


def _face_recognition():
    if "fr" not in _state:
        import face_recognition  # type: ignore
        _state["fr"] = face_recognition
    return _state["fr"]


def _qr():
    if "qr" not in _state:
        from pyzbar import pyzbar  # type: ignore
        _state["qr"] = pyzbar
    return _state["qr"]


def _ocr():
    if "ocr" not in _state:
        import pytesseract  # type: ignore
        _state["ocr"] = pytesseract
    return _state["ocr"]


def _object_net():
    """Tiny MobileNet-SSD via OpenCV DNN — bundled, no download required if
    the model files are present. Object detection reports an empty result when
    the files are missing; it never fabricates detections."""
    if "net" in _state:
        return _state["net"]
    weights = settings.data_dir / "models" / "MobileNetSSD_deploy.caffemodel"
    proto = settings.data_dir / "models" / "MobileNetSSD_deploy.prototxt"
    if weights.exists() and proto.exists():
        net = cv2.dnn.readNetFromCaffe(str(proto), str(weights))
        classes = [
            "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus",
            "car", "cat", "chair", "cow", "diningtable", "dog", "horse",
            "motorbike", "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor",
        ]
        _state["net"] = (net, classes)
    else:
        _state["net"] = (None, None)
    return _state["net"]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

async def analyze_frame(b64_jpeg: str) -> dict[str, Any]:
    """Run every available CV pass on a frame and return a single dict."""
    img = await asyncio.to_thread(_decode, b64_jpeg)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def _faces():
        try:
            fr = _face_recognition()
            locations = fr.face_locations(rgb, model="hog")
            encodings = fr.face_encodings(rgb, locations)
            out = []
            for (top, right, bottom, left), enc in zip(locations, encodings):
                name = _match_face(enc)
                out.append({"name": name, "box": [int(left), int(top), int(right), int(bottom)]})
            return out
        except Exception as exc:
            log.debug("face_recognition failed: %s", exc)
            return []

    def _hands():
        try:
            mp = _mediapipe()
            with mp.solutions.hands.Hands(static_image_mode=True, max_num_hands=2) as hands:
                res = hands.process(rgb)
                if not res.multi_hand_landmarks:
                    return []
                return [
                    {
                        "handedness": h.classification[0].label,
                        "landmarks": [
                            {"x": lm.x, "y": lm.y, "z": lm.z}
                            for lm in hand.landmark
                        ],
                    }
                    for h, hand in zip(res.multi_handedness, res.multi_hand_landmarks)
                ]
        except Exception as exc:
            log.debug("mediapipe hands failed: %s", exc)
            return []

    def _pose():
        try:
            mp = _mediapipe()
            with mp.solutions.pose.Pose(static_image_mode=True) as pose:
                res = pose.process(rgb)
                if not res.pose_landmarks:
                    return None
                return [
                    {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
                    for lm in res.pose_landmarks.landmark
                ]
        except Exception as exc:
            log.debug("pose failed: %s", exc)
            return None

    def _qr_codes():
        try:
            pyzbar = _qr()
            decoded = pyzbar.decode(img)
            return [{"type": d.type, "data": d.data.decode("utf-8", errors="ignore")} for d in decoded]
        except Exception as exc:
            log.debug("qr decode failed: %s", exc)
            return []

    def _ocr_text():
        try:
            tess = _ocr()
            text = tess.image_to_string(img)
            return text.strip()
        except Exception as exc:
            log.debug("ocr failed: %s", exc)
            return ""

    def _objects():
        net, classes = _object_net()
        if net is None:
            return []
        blob = cv2.dnn.blobFromImage(cv2.resize(img, (300, 300)), 0.007843, (300, 300), 127.5)
        net.setInput(blob)
        detections = net.forward()
        found: list[dict[str, Any]] = []
        for i in range(detections.shape[2]):
            conf = float(detections[0, 0, i, 2])
            if conf > 0.5:
                idx = int(detections[0, 0, i, 1])
                label = classes[idx] if idx < len(classes) else "object"
                box = detections[0, 0, i, 3:7] * np.array([img.shape[1], img.shape[0], img.shape[1], img.shape[0]])
                found.append({
                    "label": label,
                    "confidence": round(conf, 3),
                    "box": [float(b) for b in box],
                })
        return found

    faces, hands, pose, qr, ocr, objects = await asyncio.gather(
        asyncio.to_thread(_faces),
        asyncio.to_thread(_hands),
        asyncio.to_thread(_pose),
        asyncio.to_thread(_qr_codes),
        asyncio.to_thread(_ocr_text),
        asyncio.to_thread(_objects),
    )

    description = _describe_scene(faces, objects, ocr, qr)

    return {
        "ts": time.time(),
        "size": {"w": int(img.shape[1]), "h": int(img.shape[0])},
        "faces": faces,
        "hands": hands,
        "pose": pose,
        "qr": qr,
        "text": ocr,
        "objects": objects,
        "description": description,
    }


def _describe_scene(faces, objects, ocr_text: str, qr) -> str:
    parts: list[str] = []
    if faces:
        names = [f["name"] for f in faces]
        parts.append(
            f"Foram detectados {len(names)} rosto(s)"
            + (f" — {', '.join(names)}." if names else ".")
        )
    if objects:
        labels = sorted({o["label"] for o in objects})
        parts.append("Objetos detectados: " + ", ".join(labels) + ".")
    if ocr_text:
        snippet = ocr_text.splitlines()[0][:120]
        parts.append(f"O texto visível começa com: \"{snippet}\".")
    if qr:
        parts.append(
            "QR/código de barras detectado: "
            + ", ".join(f"{q['type']}:{q['data']}" for q in qr)
        )
    if not parts:
        return "Nenhum elemento relevante foi detectado na cena."
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Face library
# --------------------------------------------------------------------------- #

def _safe_face_name(name: str) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", str(name or "")).strip()
    if not display or len(display) > 80:
        raise ValueError("O nome precisa ter entre 1 e 80 caracteres.")
    if any(char in {"/", "\\", ":", "\0"} or unicodedata.category(char).startswith("C") for char in display):
        raise ValueError("O nome contém caracteres não permitidos.")
    slug_chars = [
        char.casefold() if char.isalnum() else "_"
        for char in display
        if char.isalnum() or char in {" ", "_", "-"}
    ]
    slug = "".join(slug_chars).strip("_-")
    while "__" in slug:
        slug = slug.replace("__", "_")
    if not slug or len(slug) > 80:
        raise ValueError("O nome não gera um identificador de face válido.")
    return display, slug


def enroll_face(name: str, b64_jpeg: str, overwrite: bool = False) -> dict[str, Any]:
    """Add a face encoding to the persistent library."""
    try:
        display_name, slug = _safe_face_name(name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "blocked": True}
    img = _decode(b64_jpeg)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    fr = _face_recognition()
    encs = fr.face_encodings(rgb)
    if not encs:
        return {"ok": False, "error": "Nenhum rosto foi encontrado na imagem."}
    faces_root = settings.faces_dir.resolve()
    out = (faces_root / f"{slug}.npy").resolve()
    try:
        out.relative_to(faces_root)
    except ValueError:
        return {"ok": False, "error": "Caminho de face inválido.", "blocked": True}
    if out.exists() and not overwrite:
        return {
            "ok": False,
            "conflict": True,
            "requires_overwrite": True,
            "error": "Já existe uma face com esse nome.",
        }
    np.save(out, encs[0])
    return {"ok": True, "name": display_name, "path": str(out)}


def _match_face(encoding) -> str:
    """Best-effort match against the face library."""
    best_name = "UNKNOWN"
    best_dist = 0.6  # face_recognition default threshold
    fr = _face_recognition()
    for f in settings.faces_dir.glob("*.npy"):
        try:
            ref = np.load(f)
            dist = float(fr.face_distance([ref], encoding)[0])
            if dist < best_dist:
                best_dist = dist
                best_name = f.stem.replace("_", " ").title()
        except Exception:
            continue
    return best_name


def list_enrolled_faces() -> list[str]:
    return [f.stem.replace("_", " ").title() for f in settings.faces_dir.glob("*.npy")]
