# Architecture

AI Art Assistant is a Krita Python docker (side panel). There is no separate server. The plugin talks to Krita on the UI thread and sends pictures to OpenAI from a background thread.

## Pipeline

```
visible canvas capture
        +
selection stencil (optional, inverted for OpenAI)
        |
        v
crop to selection plus margin (if any)
        |
        v
enlarge crop so the sketch fills OpenAI's min size (no empty-canvas pad, no mask)
        |
        v
HTTPS POST /v1/images/edits  (one click, one image)
        |
        v
scale back to crop, paste at origin, then clip to Generate-time stencil
(AI RGB, alpha = coverage)
        |
        v
candidate preview (transparent outside the box)
        |
        v
new Krita paint layer if you Apply (undoable)
```

With a selection, the upload is the selected sketch plus a 64px real-pixel margin. If that crop is smaller than OpenAI’s minimum, it is enlarged so the doodle fills the frame (then scaled back). No mask is sent; a mask tells GPT Image to replace a hole. Local clip is what keeps unselected pixels off the new layer. No selection means the full image is sent, previewed, and applied.

## Modules

| Piece | Role | Status |
|---|---|---|
| Plugin bootstrap (`__init__.py`, `.desktop`) | Register the docker with Krita | Phase 0 |
| Panel (`docker.py`) | Document info, export, import, Generate, Cancel, preview | Phase 4a |
| Krita document adapter (`krita_document.py`) | Projection, selection, layer insert, overlay clip, crop/paste | Phase 4a |
| Image pipeline (`image_pipeline.py`) | PNG size checks, coverage, mask invert, clip, crop rect | Phase 4a |
| Prompts (`prompts.py`) | Base prompt + rules + instruction; selection is a whole-sketch edit | Phase 4a |
| Credentials (`credentials.py`) | Windows Credential Manager / session key | Phase 2 |
| Settings (`settings.py`) | Non-secret defaults, prompt history, request log, flare/sunburst | Phase 4a |
| OpenAI adapter (`openai_provider.py`) | Stdlib HTTPS Image Edit | Phase 2 |
| Strict selection composite | Clip applied pixels to the Generate-time stencil | Phase 3 |

## Development install

`scripts/link_plugin_for_dev.ps1` creates a Windows junction from `%APPDATA%\krita\pykrita\ai_art_assistant` to this repo's `ai_art_assistant` folder, and a file link for `ai_art_assistant.desktop`. Restart Krita after code changes.

## What this repo will not include

API keys, `.kra` documents, or game artwork.
