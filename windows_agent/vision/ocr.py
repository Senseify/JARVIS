"""Optical Character Recognition (OCR) engine for structured text extraction from observations."""

import asyncio
import json
import logging
import shutil
import subprocess
import sys
from typing import Callable, List, Optional

from windows_agent.observation.store import ObservationStore
from windows_agent.vision.cache import VisionCache
from windows_agent.vision.models import BoundingBox, TextRegion

logger = logging.getLogger(__name__)


class OCREngine:
    """Request-driven OCR engine operating on stored screenshot observations."""

    def __init__(
        self,
        store: ObservationStore,
        cache: Optional[VisionCache] = None,
        custom_provider: Optional[Callable[[str, str], List[TextRegion]]] = None,
    ):
        self.store = store
        self.cache = cache or VisionCache()
        self.custom_provider = custom_provider
        self.is_windows = sys.platform == "win32"

    async def extract_text(self, observation_id: str) -> List[TextRegion]:
        """Extract structured text regions from the specified observation."""
        # 1. Check cache first
        cached = self.cache.get_ocr(observation_id)
        if cached is not None:
            return cached

        # 2. Verify observation exists
        record = self.store.get(observation_id)
        if not record:
            raise ValueError(f"Observation ID '{observation_id}' not found in observation store.")

        image_path = record.get("file_path")
        if not image_path:
            raise ValueError(f"No file path recorded for observation '{observation_id}'.")

        # 3. Custom provider override (primarily for unit/integration tests)
        if self.custom_provider is not None:
            regions = await asyncio.to_thread(self.custom_provider, observation_id, image_path)
            self.cache.set_ocr(observation_id, regions)
            return regions

        # 4. Native Windows Media OCR execution
        if self.is_windows:
            regions = await asyncio.to_thread(self._run_windows_ocr, observation_id, image_path)
            self.cache.set_ocr(observation_id, regions)
            return regions

        # 5. Non-Windows platform handling
        logger.debug(f"OCR requested on non-Windows platform '{sys.platform}'. Returning empty regions.")
        empty_regions: List[TextRegion] = []
        self.cache.set_ocr(observation_id, empty_regions)
        return empty_regions

    def _run_windows_ocr(self, observation_id: str, image_path: str) -> List[TextRegion]:
        """Invoke Windows 10/11 native WinRT OCR via PowerShell bridge."""
        ps_script = f"""
        [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
        [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
        [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
        [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]

        Function Await($asyncOp, $type) {{
            $netTask = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($asyncOp))
            $netTask.Wait(-1) | Out-Null
            return $netTask.Result
        }}

        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync('{image_path}')) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        $result = Await ($ocr.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

        $items = @()
        foreach ($line in $result.Lines) {{
            $rect = $line.Words[0].BoundingRect
            $items += @{{
                text = $line.Text
                left = [int]$rect.X
                top = [int]$rect.Y
                width = [int]$rect.Width
                height = [int]$rect.Height
            }}
        }}
        $items | ConvertTo-Json -Compress
        """

        try:
            cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode != 0 or not proc.stdout.strip():
                logger.warning(f"Windows OCR script completed without output: {proc.stderr}")
                return []

            raw_data = json.loads(proc.stdout.strip())
            if isinstance(raw_data, dict):
                raw_data = [raw_data]

            results = []
            for item in raw_data:
                bbox = None
                if all(k in item for k in ("left", "top", "width", "height")) and item["width"] > 0 and item["height"] > 0:
                    bbox = BoundingBox(
                        left=int(item["left"]),
                        top=int(item["top"]),
                        width=int(item["width"]),
                        height=int(item["height"]),
                    )
                results.append(
                    TextRegion(
                        text=str(item.get("text", "")).strip(),
                        bounding_box=bbox,
                        confidence=0.95,
                        observation_id=observation_id,
                    )
                )
            return results

        except Exception as e:
            logger.warning(f"Failed to execute Windows Media OCR: {e}")
            return []
