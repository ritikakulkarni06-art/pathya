"""Real library and native-binding smoke tests; no model inference/downloads."""

from __future__ import annotations

import importlib.metadata as metadata
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def test_installed_environment_matches_pins_and_one_opencv_distribution() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_environment.py")],
                            capture_output=True, text=True, timeout=30, check=True)
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["opencv_distributions"] == ["opencv-python-headless"]
    assert report["model_inference_verified"] is False


def test_pdfium_native_binary_and_image_stack() -> None:
    import cv2
    import numpy as np
    import pypdfium2 as pdfium

    # Entirely synthetic blank page: proves binary/loading compatibility only.
    # pypdfium2 5.x objects are not context managers; close explicitly.
    document = pdfium.PdfDocument.new()
    page = bitmap = None
    try:
        page = document.new_page(72, 72)
        bitmap = page.render(scale=1)
        image = bitmap.to_pil().copy()
    finally:
        for obj in (bitmap, page, document):
            if obj is not None:
                obj.close()
    assert image.size == (72, 72)
    rgb = np.asarray(image.convert("RGB"))
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    assert grey.shape == (72, 72)
    assert grey.min() == 255


def test_pdf_ocr_and_schema_libraries_import() -> None:
    import pdfplumber
    import pytesseract
    from jsonschema import Draft202012Validator
    from pydantic import BaseModel

    # Availability only: no source PDF, OCR call or application schema yet.
    assert callable(pdfplumber.open)
    assert callable(pytesseract.image_to_data)
    assert callable(BaseModel.model_json_schema)
    assert callable(Draft202012Validator.check_schema)


def test_docling_converter_imports_without_network_or_model_files(tmp_path: Path) -> None:
    code = """
import os, pathlib, socket
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HOME'] = str(pathlib.Path.cwd() / 'huggingface')
def deny_network(*args, **kwargs):
    raise RuntimeError('Network access forbidden in dependency import test')
socket.socket.connect = deny_network
socket.create_connection = deny_network
from docling.document_converter import DocumentConverter
assert callable(DocumentConverter)
assert not list(pathlib.Path('.').rglob('*.safetensors'))
assert not list(pathlib.Path('.').rglob('*.onnx'))
print('Docling import OK; no converter/model instantiated.')
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=tmp_path,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Docling import OK" in result.stdout


def test_pip_dependency_consistency() -> None:
    result = subprocess.run([sys.executable, "-m", "pip", "check"],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

