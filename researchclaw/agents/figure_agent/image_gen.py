"""Image Generation Agent — multi-backend conceptual figure generation.

Generates non-data figures (architecture diagrams, flowcharts, pipeline
overviews, concept illustrations) using one of several backends:

  1. **gemini** — Google Gemini native image generation (Nano Banana)
     Requires: ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY`` env var
     Quality: ⭐⭐⭐⭐⭐

  2. **openai_image** — OpenAI /v1/images/generations (DALL-E 3 / gpt-image-1)
     Requires: ``OPENAI_API_KEY`` or OpenAI-compatible endpoint
     Quality: ⭐⭐⭐⭐

  3. **smart_excalidraw** — Smart-Excalidraw FastAPI backend
     Requires: Smart-Excalidraw server running (``uvicorn app.main:app``)
     Quality: ⭐⭐⭐⭐⭐  (best for flowcharts/architecture diagrams)
     Features: multi-agent planning + generation + optimization + validation

  4. **excalidraw_llm** — LLM generates Excalidraw JSON → render to PNG/SVG
     Requires: Any LLM (Claude, GPT, etc.) + ``Excalidraw-Interface`` package
     Quality: ⭐⭐⭐⭐  (good for flowcharts/architecture diagrams)

  5. **matplotlib_fallback** — LLM generates matplotlib script for simplified
     structural diagrams
     Requires: Any LLM + matplotlib
     Quality: ⭐⭐  (last resort)

The agent automatically selects the best available backend based on
configured API keys and installed packages.  When a backend fails, it
falls back to the next one in the priority chain.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from researchclaw.agents.base import BaseAgent, AgentStepResult
from researchclaw.utils.sanitize import sanitize_figure_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend priority order
# ---------------------------------------------------------------------------

BACKEND_GEMINI = "gemini"
BACKEND_OPENAI_IMAGE = "openai_image"
BACKEND_SMART_EXCALIDRAW = "smart_excalidraw"
BACKEND_EXCALIDRAW_LLM = "excalidraw_llm"
BACKEND_MATPLOTLIB_FALLBACK = "matplotlib_fallback"

BACKEND_PRIORITY = [
    BACKEND_GEMINI,
    BACKEND_OPENAI_IMAGE,
    BACKEND_SMART_EXCALIDRAW,
    BACKEND_EXCALIDRAW_LLM,
    BACKEND_MATPLOTLIB_FALLBACK,
]

_EXCALIDRAW_CHART_TYPE_MAP = {
    "architecture_diagram": "architecture",
    "method_flowchart": "flowchart",
    "pipeline_overview": "flowchart",
    "concept_illustration": "mindmap",
    "system_diagram": "architecture",
    "attention_visualization": "architecture",
    "comparison_illustration": "flowchart",
}

# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

_GEMINI_DEFAULT_MODEL = "gemini-2.5-flash-image"
_GEMINI_FALLBACK_MODELS = [
    "gemini-2.0-flash-exp-image-generation",
    "gemini-1.5-flash",
]

_OPENAI_IMAGE_DEFAULT_MODEL = "gpt-image-1"
_OPENAI_IMAGE_FALLBACK_MODELS = ["dall-e-3", "dall-e-2"]

_ACADEMIC_STYLE_PROMPT = (
    "The image should be in a clean, professional ACADEMIC style suitable "
    "for a top-tier AI/ML research paper (NeurIPS, ICML, ICLR). "
    "Use a white or light background. Use clear labels and annotations. "
    "Avoid excessive decoration. Use a consistent color palette. "
    "Text should be legible at column width (~3.25 inches). "
    "Style: technical illustration, vector-like, clean lines."
)

_EXCALIDRAW_SYSTEM_PROMPT = """\
You are an expert at creating Excalidraw diagrams in JSON format for \
ACADEMIC RESEARCH PAPERS (NeurIPS, ICML, ICLR style).
Given a description of an academic figure, generate a valid Excalidraw
JSON array of elements.

ARCHITECTURE:
- The diagram should have a clear top-to-bottom or left-to-right flow
- Use consistent spacing: 180px horizontal, 120px vertical between elements
- Start the first element at approximately (100, 80)
- Group related elements with similar x or y coordinates

ELEMENT TYPES AND RULES:

1. **rectangle** — For process blocks, modules, layers
   - Standard size: width=200, height=60 for labels
   - Wide size: width=280, height=60 for longer text
   - Use light fill colors: #e8f4f8 (blue), #f0e8f8 (purple), #e8f8e8 (green)
   - strokeColor: "#1e1e1e", strokeWidth: 2, roughness: 0
   - roundness: {"type": 3}

2. **diamond** — For decision points, conditional logic
   - Size: width=160, height=100
   - backgroundColor: "#fff8e8" (yellow)
   - Place text as a separate text element centered inside

3. **ellipse** — For start/end nodes, data sources
   - Size: width=140, height=60
   - backgroundColor: "#e8f8e8" (green) for start, "#f8e8e8" (red) for end

4. **text** — For labels inside boxes and standalone annotations
   - fontSize: 18 for main labels, 14 for sub-labels
   - fontFamily: 1 (Helvetica)
   - textAlign: "center"
   - Place text element at (box.x + box.width/2 - text_width/2, box.y + box.height/2 - 10)
   - For text inside a box, create a separate text element with the same groupIds

5. **arrow** — For connections between elements
   - Use startBinding and endBinding to connect elements by id
   - points: [[0,0], [dx, dy]] where dx,dy is the offset to the target
   - strokeColor: "#1e1e1e", strokeWidth: 2
   - startArrowhead: null, endArrowhead: "arrow"
   - roughness: 0
   - For labels on arrows, add a separate text element near the midpoint

6. **line** — For grouping borders or dividers
   - strokeColor: "#999999", strokeWidth: 1, strokeStyle: "dashed"

COLOR PALETTE (academic, colorblind-safe):
- Primary boxes:   #e8f4f8 (light blue)
- Secondary boxes: #f0e8f8 (light purple)
- Accent boxes:    #e8f8e8 (light green)
- Decision:        #fff8e8 (light yellow)
- End/Error:        #f8e8e8 (light red)
- Arrows/lines:    #1e1e1e (near black)
- Text:            #1e1e1e

REQUIRED FIELDS PER ELEMENT:
- type, id (unique string like "box1", "arrow1", "text1")
- x, y (integer coordinates)
- width, height (integer dimensions)
- strokeColor, backgroundColor (hex strings)
- fillStyle: "solid" or "hachure"
- strokeWidth (integer)
- roughness: 0 (for clean academic look)
- opacity: 100
- angle: 0
- groupIds: [] (use same groupIds for box + its text label)
- locked: false

OUTPUT FORMAT:
- Output ONLY a JSON array of Excalidraw element objects
- No markdown fences, no explanation
- Ensure all arrow bindings reference valid element ids
- Every element must have a unique id
- Text elements for box labels must be positioned inside their parent box

EXAMPLE (simple 3-step pipeline):
[
  {"type":"rectangle","id":"input","x":100,"y":80,"width":200,"height":60,"strokeColor":"#1e1e1e","backgroundColor":"#e8f8e8","fillStyle":"solid","strokeWidth":2,"roughness":0,"opacity":100,"angle":0,"groupIds":[],"locked":false,"roundness":{"type":3}},
  {"type":"text","id":"input_label","x":140,"y":100,"width":120,"height":25,"text":"Input Data","fontSize":18,"fontFamily":1,"textAlign":"center","strokeColor":"#1e1e1e","backgroundColor":"transparent","fillStyle":"solid","strokeWidth":1,"roughness":0,"opacity":100,"angle":0,"groupIds":[],"locked":false},
  {"type":"rectangle","id":"process","x":100,"y":260,"width":200,"height":60,"strokeColor":"#1e1e1e","backgroundColor":"#e8f4f8","fillStyle":"solid","strokeWidth":2,"roughness":0,"opacity":100,"angle":0,"groupIds":[],"locked":false,"roundness":{"type":3}},
  {"type":"text","id":"process_label","x":130,"y":280,"width":140,"height":25,"text":"Model Layer","fontSize":18,"fontFamily":1,"textAlign":"center","strokeColor":"#1e1e1e","backgroundColor":"transparent","fillStyle":"solid","strokeWidth":1,"roughness":0,"opacity":100,"angle":0,"groupIds":[],"locked":false},
  {"type":"arrow","id":"arrow1","x":200,"y":140,"width":0,"height":120,"points":[[0,0],[0,120]],"startBinding":{"elementId":"input","focus":0,"gap":5},"endBinding":{"elementId":"process","focus":0,"gap":5},"strokeColor":"#1e1e1e","strokeWidth":2,"roughness":0,"opacity":100,"angle":0,"groupIds":[],"locked":false,"startArrowhead":null,"endArrowhead":"arrow"}
]
"""

_MATPLOTLIB_DIAGRAM_SYSTEM_PROMPT = """\
You are an expert at creating academic diagrams using matplotlib.
Given a description of a figure, generate a complete Python script that
creates a clean, professional diagram (flowchart, architecture, etc.)
using matplotlib patches, annotations, and arrows.

RULES:
- Use matplotlib.patches (FancyBboxPatch, FancyArrowPatch) for boxes and arrows
- Use ax.text() for labels
- Use a white background, no grid
- Use professional colors (blues, grays, light fills)
- Set figure size to (10, 6) or appropriate aspect ratio
- Save to the path specified in the script
- The script must be self-contained and runnable
- Output ONLY the Python code, no explanation
"""


def _detect_available_backends(
    *,
    gemini_api_key: str = "",
    openai_api_key: str = "",
    openai_base_url: str = "",
    smart_excalidraw_url: str = "",
    llm_available: bool = True,
) -> list[str]:
    """Detect which backends are available based on keys and packages."""
    available: list[str] = []

    # Gemini
    gemini_key = (
        gemini_api_key
        or os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
    )
    if gemini_key:
        available.append(BACKEND_GEMINI)

    # OpenAI Image
    openai_key = (
        openai_api_key
        or os.environ.get("OPENAI_API_KEY", "")
    )
    if openai_key or openai_base_url:
        available.append(BACKEND_OPENAI_IMAGE)

    # Smart-Excalidraw (FastAPI server)
    se_url = (
        smart_excalidraw_url
        or os.environ.get("SMART_EXCALIDRAW_URL", "")
    )
    if se_url:
        available.append(BACKEND_SMART_EXCALIDRAW)

    # Excalidraw LLM (needs LLM + optional Excalidraw-Interface package)
    if llm_available:
        available.append(BACKEND_EXCALIDRAW_LLM)

    # Matplotlib fallback (needs LLM + matplotlib)
    if llm_available:
        available.append(BACKEND_MATPLOTLIB_FALLBACK)

    return available


class ImageGenAgent(BaseAgent):
    """Multi-backend image generation for conceptual/architectural figures.

    Automatically selects the best available backend and falls back
    through the priority chain on failure.
    """

    name = "image_gen"

    def __init__(
        self,
        llm: Any,
        *,
        gemini_api_key: str | None = None,
        gemini_model: str = _GEMINI_DEFAULT_MODEL,
        openai_api_key: str | None = None,
        openai_base_url: str | None = None,
        openai_image_model: str = _OPENAI_IMAGE_DEFAULT_MODEL,
        smart_excalidraw_url: str | None = None,
        smart_excalidraw_config: dict[str, Any] | None = None,
        output_dir: str | Path | None = None,
        aspect_ratio: str = "16:9",
        preferred_backend: str | None = None,
        use_sdk: bool | None = None,
    ) -> None:
        super().__init__(llm)

        self._gemini_api_key = (
            gemini_api_key
            or os.environ.get("GEMINI_API_KEY", "")
            or os.environ.get("GOOGLE_API_KEY", "")
        )
        self._gemini_model = gemini_model
        self._openai_api_key = (
            openai_api_key
            or os.environ.get("OPENAI_API_KEY", "")
        )
        self._openai_base_url = (
            openai_base_url
            or os.environ.get("OPENAI_IMAGE_BASE_URL", "")
        )
        self._openai_image_model = openai_image_model
        self._smart_excalidraw_url = (
            smart_excalidraw_url
            or os.environ.get("SMART_EXCALIDRAW_URL", "")
        )
        self._smart_excalidraw_config = smart_excalidraw_config or {}
        self._output_dir = Path(output_dir) if output_dir else None
        self._aspect_ratio = aspect_ratio
        self._preferred_backend = preferred_backend

        self._use_sdk = use_sdk
        if self._use_sdk is None:
            try:
                import google.genai  # noqa: F401
                self._use_sdk = True
            except ImportError:
                self._use_sdk = False

        self._available_backends = _detect_available_backends(
            gemini_api_key=self._gemini_api_key,
            openai_api_key=self._openai_api_key,
            openai_base_url=self._openai_base_url,
            smart_excalidraw_url=self._smart_excalidraw_url,
            llm_available=llm is not None,
        )

        if not self._gemini_api_key:
            logger.info("No Gemini API key — gemini backend disabled")
        if not self._openai_api_key and not self._openai_base_url:
            logger.info("No OpenAI API key — openai_image backend disabled")
        if not self._smart_excalidraw_url:
            logger.info("No Smart-Excalidraw URL — smart_excalidraw backend disabled")

        logger.info(
            "ImageGenAgent available backends: %s",
            self._available_backends,
        )

    @property
    def available_backends(self) -> list[str]:
        return list(self._available_backends)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, context: dict[str, Any]) -> AgentStepResult:
        """Generate images for figure decisions marked as 'image' backend.

        Context keys:
            image_figures (list[dict]): Decisions with backend="image"
            topic (str): Research topic
            output_dir (str|Path): Output directory for images
        """
        image_figures = context.get("image_figures", [])
        topic = context.get("topic", "")
        output_dir = Path(
            context.get("output_dir", self._output_dir or "charts")
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        if not image_figures:
            return self._make_result(
                success=True,
                data={"generated": [], "count": 0},
            )

        if not self._available_backends:
            return self._make_result(
                success=False,
                error="No image generation backend available",
                data={"generated": [], "count": 0},
            )

        generated: list[dict[str, Any]] = []

        for i, fig in enumerate(image_figures):
            figure_id = sanitize_figure_id(
                fig.get("figure_id", f"conceptual_{i + 1}")
            )
            description = fig.get("description", "")
            figure_type = fig.get("figure_type", "architecture_diagram")
            section = fig.get("section", "Method")

            result_entry = self._generate_with_fallback(
                figure_id=figure_id,
                description=description,
                figure_type=figure_type,
                section=section,
                topic=topic,
                output_dir=output_dir,
            )
            generated.append(result_entry)

        success_count = sum(1 for g in generated if g.get("success"))

        return self._make_result(
            success=success_count > 0,
            data={
                "generated": generated,
                "count": success_count,
                "total_attempted": len(image_figures),
            },
        )

    # ------------------------------------------------------------------
    # Fallback chain
    # ------------------------------------------------------------------

    def _generate_with_fallback(
        self,
        *,
        figure_id: str,
        description: str,
        figure_type: str,
        section: str,
        topic: str,
        output_dir: Path,
    ) -> dict[str, Any]:
        """Try backends in priority order until one succeeds."""
        backends = list(self._available_backends)

        if self._preferred_backend and self._preferred_backend in backends:
            backends.remove(self._preferred_backend)
            backends.insert(0, self._preferred_backend)

        errors: list[str] = []

        for backend in backends:
            output_path = output_dir / f"{figure_id}.png"
            prompt = self._build_prompt(
                description=description,
                figure_type=figure_type,
                section=section,
                topic=topic,
                backend=backend,
            )

            try:
                success = self._dispatch_backend(
                    backend=backend,
                    prompt=prompt,
                    output_path=output_path,
                    figure_type=figure_type,
                    description=description,
                    topic=topic,
                )

                if success:
                    logger.info(
                        "Generated %s via %s: %s",
                        figure_id, backend, output_path,
                    )
                    return {
                        "figure_id": figure_id,
                        "figure_type": figure_type,
                        "section": section,
                        "description": description,
                        "output_path": str(output_path),
                        "path": str(output_path),
                        "title": description[:80] if description else f"Figure {figure_id}",
                        "caption": description or "",
                        "prompt": prompt,
                        "success": True,
                        "backend": backend,
                    }

            except Exception as e:
                err_msg = f"{backend}: {e}"
                errors.append(err_msg)
                logger.warning(
                    "Backend %s failed for %s: %s",
                    backend, figure_id, e,
                )

        return {
            "figure_id": figure_id,
            "figure_type": figure_type,
            "section": section,
            "description": description,
            "success": False,
            "error": "; ".join(errors),
            "backend": "none",
        }

    def _dispatch_backend(
        self,
        *,
        backend: str,
        prompt: str,
        output_path: Path,
        figure_type: str,
        description: str,
        topic: str,
    ) -> bool:
        """Route to the appropriate backend method."""
        if backend == BACKEND_GEMINI:
            return self._generate_via_gemini(prompt, output_path)
        elif backend == BACKEND_OPENAI_IMAGE:
            return self._generate_via_openai_image(prompt, output_path)
        elif backend == BACKEND_SMART_EXCALIDRAW:
            return self._generate_via_smart_excalidraw(
                description=description,
                figure_type=figure_type,
                topic=topic,
                output_path=output_path,
            )
        elif backend == BACKEND_EXCALIDRAW_LLM:
            return self._generate_via_excalidraw(
                description=description,
                figure_type=figure_type,
                topic=topic,
                output_path=output_path,
            )
        elif backend == BACKEND_MATPLOTLIB_FALLBACK:
            return self._generate_via_matplotlib(
                description=description,
                figure_type=figure_type,
                topic=topic,
                output_path=output_path,
            )
        else:
            logger.error("Unknown backend: %s", backend)
            return False

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        *,
        description: str,
        figure_type: str,
        section: str,
        topic: str,
        backend: str = "gemini",
    ) -> str:
        """Build a prompt for the specified backend."""
        type_guidelines = self._get_type_guidelines(figure_type)

        if backend in (BACKEND_EXCALIDRAW_LLM, BACKEND_MATPLOTLIB_FALLBACK):
            return (
                f"Create a diagram for the '{section}' section of a "
                f"research paper about: {topic}\n\n"
                f"Figure description: {description}\n\n"
                f"Style guidelines:\n{type_guidelines}\n\n"
                f"The diagram must be clean, professional, and suitable "
                f"for a top-tier AI/ML conference paper."
            )

        if backend == BACKEND_SMART_EXCALIDRAW:
            return (
                f"Create a diagram for the '{section}' section of a "
                f"research paper about: {topic}\n\n"
                f"Figure description: {description}\n\n"
                f"Style guidelines:\n{type_guidelines}"
            )

        return (
            f"Create a professional academic figure for the '{section}' "
            f"section of a research paper about: {topic}\n\n"
            f"Figure description: {description}\n\n"
            f"Style guidelines:\n{type_guidelines}\n\n"
            f"{_ACADEMIC_STYLE_PROMPT}\n\n"
            f"The figure must be publication-ready for a top-tier "
            f"AI/ML conference paper."
        )

    @staticmethod
    def _get_type_guidelines(figure_type: str) -> str:
        guidelines = {
            "architecture_diagram": (
                "- Show the model layers, connections, and data flow\n"
                "- Use boxes for layers/modules with clear labels\n"
                "- Use arrows to show data flow direction\n"
                "- Include dimensions/shapes where relevant\n"
                "- Group related components with dashed borders\n"
                "- Use a consistent left-to-right or top-to-bottom flow"
            ),
            "method_flowchart": (
                "- Show the step-by-step process flow\n"
                "- Use rounded rectangles for processes\n"
                "- Use diamonds for decision points\n"
                "- Use arrows with labels for transitions\n"
                "- Number the steps if sequential\n"
                "- Highlight key/novel steps with color"
            ),
            "pipeline_overview": (
                "- Show the full pipeline from input to output\n"
                "- Use distinct visual blocks for each stage\n"
                "- Include example inputs/outputs at each stage\n"
                "- Use consistent arrow style for data flow\n"
                "- Label each stage clearly\n"
                "- Show parallel/branching paths if applicable"
            ),
            "concept_illustration": (
                "- Illustrate the key concept or intuition\n"
                "- Use simple, clean diagrams\n"
                "- Include before/after or problem/solution comparison\n"
                "- Use visual metaphors where appropriate\n"
                "- Keep it simple enough to understand at a glance"
            ),
            "system_diagram": (
                "- Show the overall system architecture\n"
                "- Include all major components and their interactions\n"
                "- Use standard UML-like notation where appropriate\n"
                "- Show data stores, APIs, and external services\n"
                "- Include protocols/data formats for connections"
            ),
            "attention_visualization": (
                "- Show attention weights or patterns\n"
                "- Use heatmap-style coloring for attention scores\n"
                "- Include input/output sequences\n"
                "- Label attention heads if multi-head attention\n"
                "- Use clear color scale legend"
            ),
            "comparison_illustration": (
                "- Show side-by-side comparison of approaches\n"
                "- Highlight key differences with visual cues\n"
                "- Use consistent styling across comparisons\n"
                "- Include labels for each approach\n"
                "- Use checkmarks/crosses for feature comparison"
            ),
        }
        return guidelines.get(figure_type, guidelines["concept_illustration"])

    # ==================================================================
    # Backend 1: Gemini (Nano Banana)
    # ==================================================================

    def _generate_via_gemini(
        self,
        prompt: str,
        output_path: Path,
    ) -> bool:
        """Generate image via Gemini API with model fallback."""
        models_to_try = [self._gemini_model] + [
            m for m in _GEMINI_FALLBACK_MODELS
            if m != self._gemini_model
        ]

        for model in models_to_try:
            if self._use_sdk:
                ok = self._gemini_sdk(prompt, output_path, model)
            else:
                ok = self._gemini_rest(prompt, output_path, model)

            if ok:
                return True
            logger.info("Gemini model %s failed, trying next", model)

        return False

    def _gemini_sdk(
        self,
        prompt: str,
        output_path: Path,
        model: str,
    ) -> bool:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self._gemini_api_key)
            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=self._aspect_ratio,
                    ),
                ),
            )

            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()
                    image.save(str(output_path))
                    return True

            logger.warning("Gemini SDK returned no image data for %s", model)
            return False

        except ImportError:
            logger.warning("google-genai SDK not installed, falling back to REST")
            self._use_sdk = False
            return self._gemini_rest(prompt, output_path, model)
        except Exception as e:
            logger.warning("Gemini SDK error (%s): %s", model, e)
            return self._gemini_rest(prompt, output_path, model)

    def _gemini_rest(
        self,
        prompt: str,
        output_path: Path,
        model: str,
    ) -> bool:
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
            logger.error("Invalid Gemini model name: %r", model)
            return False

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": self._aspect_ratio,
                },
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._gemini_api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            candidates = result.get("candidates", [])
            if not candidates:
                logger.warning("Gemini REST returned no candidates for %s", model)
                return False

            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                inline_data = part.get("inlineData", {})
                if inline_data.get("mimeType", "").startswith("image/"):
                    image_bytes = base64.b64decode(inline_data["data"])
                    output_path.write_bytes(image_bytes)
                    return True

            logger.warning("Gemini REST returned no image parts for %s", model)
            return False

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            logger.warning("Gemini REST error %d for %s: %s", e.code, model, body)
            return False
        except Exception as e:
            logger.warning("Gemini REST error for %s: %s", model, e)
            return False

    # ==================================================================
    # Backend 2: OpenAI Image (/v1/images/generations)
    # ==================================================================

    def _generate_via_openai_image(
        self,
        prompt: str,
        output_path: Path,
    ) -> bool:
        """Generate image via OpenAI /v1/images/generations endpoint."""
        base_url = self._openai_base_url or "https://api.openai.com/v1"
        base_url = base_url.rstrip("/")
        url = f"{base_url}/images/generations"

        models_to_try = [self._openai_image_model] + [
            m for m in _OPENAI_IMAGE_FALLBACK_MODELS
            if m != self._openai_image_model
        ]

        for model in models_to_try:
            payload = {
                "model": model,
                "prompt": prompt[:4000],
                "n": 1,
                "size": self._map_aspect_ratio_to_size(),
                "response_format": "b64_json",
            }

            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
            }
            if self._openai_api_key:
                headers["Authorization"] = f"Bearer {self._openai_api_key}"

            req = urllib.request.Request(
                url, data=data, headers=headers, method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode("utf-8"))

                images = result.get("data", [])
                if not images:
                    logger.warning("OpenAI Image returned no data for %s", model)
                    continue

                img_data = images[0]
                b64 = img_data.get("b64_json", "")
                if b64:
                    image_bytes = base64.b64decode(b64)
                    output_path.write_bytes(image_bytes)
                    return True

                img_url = img_data.get("url", "")
                if img_url:
                    return self._download_image(img_url, output_path)

                logger.warning("OpenAI Image returned no image for %s", model)

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:500]
                logger.warning(
                    "OpenAI Image error %d for %s: %s", e.code, model, body,
                )
            except Exception as e:
                logger.warning("OpenAI Image error for %s: %s", model, e)

        return False

    def _map_aspect_ratio_to_size(self) -> str:
        if self._aspect_ratio in ("16:9", "3:2", "2:1"):
            return "1792x1024"
        if self._aspect_ratio in ("9:16", "2:3", "1:2"):
            return "1024x1792"
        return "1024x1024"

    @staticmethod
    def _download_image(url: str, output_path: Path) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ResearchClaw/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                output_path.write_bytes(resp.read())
            return True
        except Exception as e:
            logger.warning("Failed to download image from %s: %s", url[:80], e)
            return False

    # ==================================================================
    # Backend 3: Smart-Excalidraw (FastAPI multi-agent server)
    # ==================================================================

    def _generate_via_smart_excalidraw(
        self,
        *,
        description: str,
        figure_type: str,
        topic: str,
        output_path: Path,
    ) -> bool:
        """Generate diagram via Smart-Excalidraw FastAPI backend.

        Smart-Excalidraw uses a multi-agent pipeline:
          1. Planner agent — analyzes requirements, selects chart type
          2. Generator agent — generates Excalidraw JSON
          3. Optimizer agent — optimizes layout, adjusts spacing
          4. Validator agent — validates JSON format and required fields

        API endpoint: POST /api/v1/generate
        """
        base_url = self._smart_excalidraw_url.rstrip("/")
        url = f"{base_url}/api/v1/generate"

        chart_type = _EXCALIDRAW_CHART_TYPE_MAP.get(figure_type, "flowchart")

        user_input = (
            f"Create a professional academic diagram for a research paper.\n\n"
            f"Topic: {topic}\n"
            f"Figure type: {figure_type}\n"
            f"Description: {description}\n\n"
            f"Requirements:\n"
            f"- Clean, professional style suitable for NeurIPS/ICML/ICLR\n"
            f"- White background, clear labels\n"
            f"- Consistent color palette (blues, grays, light fills)\n"
            f"- Top-to-bottom or left-to-right flow\n"
            f"- All text in English"
        )

        se_config = self._smart_excalidraw_config
        payload: dict[str, Any] = {
            "config": {
                "name": se_config.get("name", "ResearchClaw"),
                "type": se_config.get("type", "openai"),
                "baseUrl": se_config.get(
                    "baseUrl",
                    os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                ),
                "apiKey": se_config.get(
                    "apiKey",
                    os.environ.get("OPENAI_API_KEY", ""),
                ),
                "model": se_config.get("model", "claude-sonnet-4-20250514"),
            },
            "userInput": user_input,
            "chartType": chart_type,
            "image": None,
            "currentCode": None,
            "stream": False,
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ResearchClaw/1.0",
        }

        try:
            req = urllib.request.Request(
                url, data=data, headers=headers, method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            logger.warning(
                "Smart-Excalidraw HTTP %d: %s", e.code, body,
            )
            return False
        except urllib.error.URLError as e:
            logger.warning(
                "Smart-Excalidraw connection failed: %s", e.reason,
            )
            return False
        except Exception as e:
            logger.warning("Smart-Excalidraw error: %s", e)
            return False

        elements_json = result.get("code", "")
        if not elements_json:
            logger.warning("Smart-Excalidraw returned no code")
            return False

        elements = self._parse_excalidraw_json(elements_json)
        if not elements:
            logger.warning("Smart-Excalidraw returned invalid elements")
            return False

        excalidraw_file = output_path.with_suffix(".excalidraw")
        excalidraw_data = {
            "type": "excalidraw",
            "version": 2,
            "elements": elements,
            "appState": {
                "viewBackgroundColor": "#ffffff",
            },
        }

        try:
            excalidraw_file.write_text(
                json.dumps(excalidraw_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to write .excalidraw file: %s", e)

        return self._render_excalidraw_to_png(elements, output_path)

    # ==================================================================
    # Backend 4: Excalidraw LLM (LLM → Excalidraw JSON → PNG/SVG)
    # ==================================================================

    def _generate_via_excalidraw(
        self,
        *,
        description: str,
        figure_type: str,
        topic: str,
        output_path: Path,
    ) -> bool:
        """Use LLM to generate Excalidraw JSON, then render to PNG."""
        user_prompt = (
            f"Create an Excalidraw diagram for the following:\n\n"
            f"Topic: {topic}\n"
            f"Figure type: {figure_type}\n"
            f"Description: {description}\n\n"
            f"Generate the Excalidraw elements JSON array now."
        )

        raw = self._chat(
            _EXCALIDRAW_SYSTEM_PROMPT,
            user_prompt,
            max_tokens=4096,
            temperature=0.3,
        )

        elements = self._parse_excalidraw_json(raw)
        if not elements:
            logger.warning("Failed to parse Excalidraw JSON from LLM")
            return False

        excalidraw_file = output_path.with_suffix(".excalidraw")
        excalidraw_data = {
            "type": "excalidraw",
            "version": 2,
            "elements": elements,
            "appState": {
                "viewBackgroundColor": "#ffffff",
            },
        }

        try:
            excalidraw_file.write_text(
                json.dumps(excalidraw_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to write .excalidraw file: %s", e)

        return self._render_excalidraw_to_png(elements, output_path)

    def _parse_excalidraw_json(self, raw: str) -> list[dict[str, Any]]:
        """Parse LLM output into Excalidraw elements list."""
        import re as _re

        raw = _re.sub(r"```(?:json)?\s*\n?", "", raw)
        raw = raw.replace("```", "").strip()

        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []

        try:
            parsed = json.loads(raw[start:end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        return []

    def _render_excalidraw_to_png(
        self,
        elements: list[dict[str, Any]],
        output_path: Path,
    ) -> bool:
        """Render Excalidraw elements to PNG using available methods.

        Tries in order:
        1. Excalidraw-Interface package (highest quality)
        2. @excalidraw/utils CLI (if installed via npm)
        3. Matplotlib-based renderer (built-in fallback)
        """
        try:
            result = self._render_excalidraw_via_interface(elements, output_path)
            if result:
                return True
        except ImportError:
            pass
        except Exception as e:
            logger.warning("Excalidraw-Interface render failed: %s", e)

        try:
            result = self._render_excalidraw_via_cli(elements, output_path)
            if result:
                return True
        except Exception as e:
            logger.debug("Excalidraw CLI render not available: %s", e)

        try:
            result = self._render_excalidraw_via_script(elements, output_path)
            if result:
                return True
        except Exception as e:
            logger.warning("Excalidraw script render failed: %s", e)

        return False

    def _render_excalidraw_via_interface(
        self,
        elements: list[dict[str, Any]],
        output_path: Path,
    ) -> bool:
        """Render using Excalidraw-Interface Python package."""
        from Excalidraw_Interface import SketchBuilder

        sb = SketchBuilder()

        element_map: dict[str, Any] = {}
        arrow_elements: list[dict[str, Any]] = []

        for elem in elements:
            elem_type = elem.get("type", "")
            elem_id = elem.get("id", "")
            x = elem.get("x", 0)
            y = elem.get("y", 0)
            w = elem.get("width", 100)
            h = elem.get("height", 60)
            bg = elem.get("backgroundColor", "")
            text = elem.get("text", "")

            if elem_type == "rectangle":
                obj = sb.Rectangle(x=x, y=y, width=w, height=h)
                element_map[elem_id] = obj
            elif elem_type == "diamond":
                obj = sb.Diamond(x=x, y=y, width=w, height=h)
                element_map[elem_id] = obj
            elif elem_type == "ellipse":
                obj = sb.Ellipse(x=x, y=y, width=w, height=h)
                if bg:
                    obj.backgroundColor = bg
                element_map[elem_id] = obj
            elif elem_type == "text":
                obj = sb.Text(text, x=x, y=y)
                element_map[elem_id] = obj
            elif elem_type == "arrow":
                arrow_elements.append(elem)

        for arrow in arrow_elements:
            start_binding = arrow.get("startBinding", {})
            end_binding = arrow.get("endBinding", {})
            start_id = start_binding.get("elementId", "")
            end_id = end_binding.get("elementId", "")

            if start_id in element_map and end_id in element_map:
                sb.create_binding_arrows(
                    element_map[start_id], element_map[end_id],
                )

        excalidraw_path = output_path.with_suffix(".excalidraw")
        sb.export_to_file(str(excalidraw_path))

        json_data = sb.export_to_json()
        if isinstance(json_data, str):
            elements_data = json.loads(json_data)
        else:
            elements_data = json_data

        return self._render_excalidraw_via_script(
            elements_data if isinstance(elements_data, list) else elements,
            output_path,
        )

    def _render_excalidraw_via_cli(
        self,
        elements: list[dict[str, Any]],
        output_path: Path,
    ) -> bool:
        """Render using @excalidraw/utils CLI (npm package).

        This provides high-quality SVG/PNG export using the official
        Excalidraw rendering engine via Node.js.
        """
        excalidraw_data = {
            "type": "excalidraw",
            "version": 2,
            "elements": elements,
            "appState": {"viewBackgroundColor": "#ffffff"},
        }

        tmp_json = output_path.with_suffix(".tmp.excalidraw")
        tmp_json.write_text(
            json.dumps(excalidraw_data, ensure_ascii=False),
            encoding="utf-8",
        )

        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "excalidraw_export",
                    str(tmp_json),
                    "--output", str(output_path),
                    "--format", "png",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and output_path.exists():
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception:
            pass

        svg_path = output_path.with_suffix(".svg")
        try:
            tmp_json_str = str(tmp_json).replace("\\", "\\\\")
            svg_path_str = str(svg_path).replace("\\", "\\\\")
            script = (
                "const fs = require('fs');\n"
                "const { exportToSvg, exportToBlob } = require('@excalidraw/utils');\n"
                f"const data = JSON.parse(fs.readFileSync('{tmp_json_str}', 'utf8'));\n"
                "const elements = data.elements || [];\n"
                "const appState = data.appState || {};\n"
                "exportToSvg({elements, appState, files: null}).then(svg => {\n"
                f"  fs.writeFileSync('{svg_path_str}', svg.outerHTML);\n"
                "  process.exit(0);\n"
                "}).catch(e => {{ console.error(e); process.exit(1); }});\n"
            )
            script_path = output_path.with_suffix(".tmp.mjs")
            script_path.write_text(script, encoding="utf-8")

            result = subprocess.run(
                ["node", str(script_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and svg_path.exists():
                return self._svg_to_png(svg_path, output_path)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception:
            pass
        finally:
            for p in (script_path, tmp_json, svg_path):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

        return False

    @staticmethod
    def _svg_to_png(svg_path: Path, png_path: Path) -> bool:
        """Convert SVG to PNG using cairosvg or Pillow."""
        try:
            import cairosvg
            cairosvg.svg2png(
                url=str(svg_path),
                write_to=str(png_path),
                dpi=300,
            )
            return png_path.exists()
        except ImportError:
            pass
        except Exception as e:
            logger.debug("cairosvg conversion failed: %s", e)

        try:
            from PIL import Image
            import io

            svg_bytes = svg_path.read_bytes()
            img = Image.open(io.BytesIO(svg_bytes))
            img.save(str(png_path), "PNG", dpi=(300, 300))
            return png_path.exists()
        except Exception as e:
            logger.debug("Pillow SVG conversion failed: %s", e)

        return False

    @staticmethod
    def _arrow_edge_point(
        src: dict[str, Any],
        dst: dict[str, Any],
    ) -> tuple[float, float]:
        """Calculate the edge point on *src* closest to *dst* center.

        Returns the point on the boundary of *src* that faces *dst*.
        """
        sx = src.get("x", 0)
        sy = src.get("y", 0)
        sw = src.get("width", 100)
        sh = src.get("height", 60)

        dx = dst.get("x", 0) + dst.get("width", 100) / 2
        dy = dst.get("y", 0) + dst.get("height", 60) / 2

        cx = sx + sw / 2
        cy = sy + sh / 2

        rx = sw / 2 if sw > 0 else 1
        ry = sh / 2 if sh > 0 else 1

        angle_x = (dx - cx) / rx if rx else 0
        angle_y = (dy - cy) / ry if ry else 0

        scale = max(abs(angle_x), abs(angle_y), 1e-9)
        scale = 1.0 / scale

        px = cx + angle_x * scale * rx
        py = cy + angle_y * scale * ry

        px = max(sx, min(sx + sw, px))
        py = max(sy, min(sy + sh, py))

        return px, py

    def _render_excalidraw_via_script(
        self,
        elements: list[dict[str, Any]],
        output_path: Path,
    ) -> bool:
        """Render Excalidraw elements to PNG using a matplotlib-based renderer."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
            from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
        except ImportError:
            logger.warning("matplotlib not available for Excalidraw rendering")
            return False

        if not elements:
            return False

        xs = [e.get("x", 0) for e in elements if e.get("type") != "arrow"]
        ys = [e.get("y", 0) for e in elements if e.get("type") != "arrow"]
        ws = [e.get("width", 100) for e in elements if e.get("type") != "arrow"]
        hs = [e.get("height", 60) for e in elements if e.get("type") != "arrow"]

        if not xs:
            return False

        min_x = min(xs) - 50
        min_y = min(ys) - 50
        max_x = max(x + w for x, w in zip(xs, ws)) + 50
        max_y = max(y + h for y, h in zip(ys, hs)) + 50

        fig_w = max(8, (max_x - min_x) / 100)
        fig_h = max(5, (max_y - min_y) / 100)

        fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
        ax.set_xlim(min_x, max_x)
        ax.set_ylim(max_y, min_y)
        ax.set_aspect("equal")
        ax.axis("off")
        fig.patch.set_facecolor("white")

        color_map = {
            "#e8f4f8": "#B3D9E8",
            "#f0e8f8": "#D9B3E8",
            "#e8f8e8": "#B3E8B3",
            "#f8f0e8": "#E8D9B3",
            "#f8e8e8": "#E8B3B3",
            "#fff3e0": "#FFE0B2",
            "#e3f2fd": "#BBDEFB",
            "#f3e5f5": "#CE93D8",
            "#e8f5e9": "#A5D6A7",
            "#fce4ec": "#F48FB1",
            "#fff8e1": "#FFECB3",
            "#e0f7fa": "#80DEEA",
            "#f1f8e9": "#C5E1A5",
            "#fbe9e7": "#FFAB91",
            "transparent": "#FFFFFF",
        }

        elem_by_id: dict[str, dict[str, Any]] = {}
        for elem in elements:
            eid = elem.get("id", "")
            if eid:
                elem_by_id[eid] = elem

        for elem in elements:
            etype = elem.get("type", "")
            x = elem.get("x", 0)
            y = elem.get("y", 0)
            w = elem.get("width", 100)
            h = elem.get("height", 60)
            bg = elem.get("backgroundColor", "")
            fill_color = color_map.get(bg, "#F0F0F0") if bg else "#F0F0F0"
            text = elem.get("text", "")

            if etype == "rectangle":
                rect = FancyBboxPatch(
                    (x, y), w, h,
                    boxstyle="round,pad=0.05",
                    facecolor=fill_color,
                    edgecolor="#333333",
                    linewidth=1.5,
                )
                ax.add_patch(rect)
                if text:
                    ax.text(
                        x + w / 2, y + h / 2, text,
                        ha="center", va="center",
                        fontsize=9, fontfamily="sans-serif",
                    )

            elif etype == "diamond":
                diamond = plt.Polygon(
                    [(x + w / 2, y), (x + w, y + h / 2),
                     (x + w / 2, y + h), (x, y + h / 2)],
                    facecolor=fill_color,
                    edgecolor="#333333",
                    linewidth=1.5,
                )
                ax.add_patch(diamond)
                if text:
                    ax.text(
                        x + w / 2, y + h / 2, text,
                        ha="center", va="center",
                        fontsize=8, fontfamily="sans-serif",
                    )

            elif etype == "ellipse":
                ellipse = mpatches.Ellipse(
                    (x + w / 2, y + h / 2), w, h,
                    facecolor=fill_color,
                    edgecolor="#333333",
                    linewidth=1.5,
                )
                ax.add_patch(ellipse)
                if text:
                    ax.text(
                        x + w / 2, y + h / 2, text,
                        ha="center", va="center",
                        fontsize=9, fontfamily="sans-serif",
                    )

            elif etype == "text":
                ax.text(
                    x, y, text,
                    ha="left", va="top",
                    fontsize=10, fontfamily="sans-serif",
                )

            elif etype == "arrow":
                points = elem.get("points", [])
                start_binding = elem.get("startBinding", {})
                end_binding = elem.get("endBinding", {})

                start_id = start_binding.get("elementId", "")
                end_id = end_binding.get("elementId", "")

                start_elem = elem_by_id.get(start_id)
                end_elem = elem_by_id.get(end_id)

                sx, sy, ex, ey = None, None, None, None

                if start_elem and end_elem:
                    sx, sy = self._arrow_edge_point(
                        start_elem, end_elem,
                    )
                    ex, ey = self._arrow_edge_point(
                        end_elem, start_elem,
                    )
                elif len(points) >= 2:
                    sx = x + points[0][0]
                    sy = y + points[0][1]
                    ex = x + points[-1][0]
                    ey = y + points[-1][1]

                if sx is not None and ex is not None:
                    ax.annotate(
                        "",
                        xy=(ex, ey), xytext=(sx, sy),
                        arrowprops=dict(
                            arrowstyle="->",
                            color="#333333",
                            lw=1.5,
                            connectionstyle="arc3,rad=0.1",
                        ),
                    )

            elif etype == "line":
                points = elem.get("points", [])
                if len(points) >= 2:
                    px = [x + p[0] for p in points]
                    py = [y + p[1] for p in points]
                    ax.plot(px, py, color="#333333", linewidth=1.5)

        plt.tight_layout(pad=0.5)
        fig.savefig(str(output_path), dpi=200, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)
        return True

    # ==================================================================
    # Backend 5: Matplotlib fallback (LLM → Python script → execute)
    # ==================================================================

    def _generate_via_matplotlib(
        self,
        *,
        description: str,
        figure_type: str,
        topic: str,
        output_path: Path,
    ) -> bool:
        """Use LLM to generate a matplotlib script for the diagram, then execute it."""
        user_prompt = (
            f"Create a matplotlib diagram for the following:\n\n"
            f"Topic: {topic}\n"
            f"Figure type: {figure_type}\n"
            f"Description: {description}\n\n"
            f"The script must save the figure to: {output_path}\n"
            f"Use matplotlib.use('Agg') at the top.\n"
            f"Output ONLY the Python code, no explanation."
        )

        raw = self._chat(
            _MATPLOTLIB_DIAGRAM_SYSTEM_PROMPT,
            user_prompt,
            max_tokens=4096,
            temperature=0.3,
        )

        code = self._extract_python_code(raw)
        if not code:
            logger.warning("Failed to extract matplotlib code from LLM")
            return False

        script_path = output_path.with_suffix(".py")
        try:
            script_path.write_text(code, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to write matplotlib script: %s", e)
            return False

        return self._execute_matplotlib_script(script_path, output_path)

    @staticmethod
    def _extract_python_code(raw: str) -> str:
        import re as _re
        m = _re.search(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
        if m:
            return m.group(1).strip()
        if "import matplotlib" in raw:
            return raw.strip()
        return ""

    @staticmethod
    def _execute_matplotlib_script(
        script_path: Path,
        expected_output: Path,
    ) -> bool:
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(
                    "Matplotlib script failed (exit %d): %s",
                    result.returncode,
                    result.stderr[:500],
                )
                return False
        except subprocess.TimeoutExpired:
            logger.warning("Matplotlib script timed out")
            return False
        except Exception as e:
            logger.warning("Matplotlib script execution error: %s", e)
            return False

        if expected_output.exists() and expected_output.stat().st_size > 0:
            return True

        logger.warning("Matplotlib script completed but no output file")
        return False
