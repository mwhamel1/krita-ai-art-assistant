# Krita AI Art Assistant

A **Krita Python plugin** for artist-controlled image editing. You sketch or paint in Krita, optionally select a region, type an instruction, and request an AI edit. The result comes back as a **new layer**. Original layers are not overwritten.

This is a public-source production tool, not a commercial product. Recruiters do not need to install Krita to read this page. A walkthrough video will be linked here when it exists.

**Pinned Krita version:** 5.3.4.1 for Windows (`C:\Program Files\Krita (x64)\`).

## How it is supposed to work

1. Capture the **visible canvas** (what Krita is showing, not a screenshot and not only one layer).
2. Capture the current **selection** as a full-size stencil when you are editing part of the image.
3. If there is a selection, **crop the upload** to that sketch plus a small real-pixel margin. If OpenAI needs a bigger image, **enlarge that sketch** so it fills the request (then scale the result back). **Composite** so applied pixels stay inside the selection. The clip is local: RGB from the AI image, alpha from the selection at Generate time.
4. Insert the result as a **new undoable layer**.

```
sketch in Krita -> panel -> visible picture + selection stencil
                 -> OpenAI Image Edit
                 -> preview, then new layer if you apply
```

Generate uploads the visible canvas, or the **selected sketch**, to OpenAI. That uses **API credits**, not a ChatGPT Plus subscription. Selection uploads send **no mask** (a mask means “replace this hole”). The plugin clips preview and Apply so pixels outside the selection never land on a new layer. A tiny box is enlarged so the doodle fills the upload, then scaled back into the box — not padded with the rest of the card.

## Implemented / Not yet

**Implemented (Phase 4a)**

- Krita docker named **AI Art Assistant**
- Document name/size and selection status
- Export visible canvas / selection stencil; import PNG as a new layer
- OpenAI Image Edit (`gpt-image-2.5-flare`): one image per Generate click
- API key in Windows Credential Manager (session-only fallback)
- Candidate preview, then Apply as new layer / Discard / Retry
- Local selection clip: preview and Apply use the box from Generate time (feathered edges stay soft)
- Crop-to-selection upload: OpenAI receives the sketch (enlarged if needed, no mask), then the result is scaled back, pasted, and clipped
- Cancel while waiting: the result is ignored (the click may still have been billed)
- Last few instructions you can reuse (saved in AppData, no pictures)
- Request log in AppData (date, document, quality, whole-canvas vs selection, ok/error). No dollar amounts
- Warn after 5 Generates this session before sending another
- Automatic tests for size, stencil coverage, mask inversion, clip, crop/paste, and fake HTTP (no paid calls)

**Not yet**

- Extra providers or multi-turn chat
- A real dollar spend cap (the log records outcome, not a price we cannot prove)
- Walkthrough video and docker screenshot

## Install (Windows, Krita 5.3.4.1)

Krita does not load plugins from this GitHub folder by itself. It loads them from:

`C:\Users\<you>\AppData\Roaming\krita\pykrita\`

### Development link (this computer)

1. Close Krita if it is open.
2. In PowerShell, from this repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\link_plugin_for_dev.ps1
```

3. Open Krita.
4. **Settings → Configure Krita → Python Plugin Manager**
5. Check **AI Art Assistant**. If there is an error next to it, the plugin failed to load (see troubleshooting).
6. Click OK, then **close and reopen Krita**.
7. You should be on the Start screen. **Do not** open **Settings → Dockers** yet; those names stay grey until a drawing exists.
8. Click **New Image** (or **File → New**), then Create. Card art is **1024 × 1536**.
9. **Settings → Dockers → AI Art Assistant** and check it so the side panel appears.

After any code change, fully restart Krita. Plugins do not live-reload.

Paste an OpenAI **API** key in the panel Settings (Windows Credential Manager). ChatGPT Plus is not enough.

### What you should see

- A side panel titled **AI Art Assistant**
- With a drawing open: the file name and size, for example `1024 × 1536`
- Generate enabled after a key is saved and a drawing is open
- Apply / Discard / Retry after a candidate returns
- With a selection: Generate uploads that sketch (enlarged if needed); preview shows only the selection; Apply puts a transparent overlay on top
- Original layers still there after Apply; Undo removes the new layer
- Cancel while Generate is running; a confirmation after five Generates this session

Exported PNGs go to `%LOCALAPPDATA%\krita-ai-art-assistant\exports\`. Do not put those files, `.kra` files, API keys, or game art into git.

Tests (no Krita, no paid API):

```powershell
py -3.14 -m unittest discover -s tests
```

## Troubleshooting

- The plugin is unchecked after restart: it crashed while loading. In Krita open **Help → Show Krita Log for Bug Reports** and look for `ai_art_assistant`.
- The panel name is grey in Dockers on the Start screen: create or open an image first, then try Dockers again.
- Generate stays grey: no drawing is open, or no API key is stored.
- OpenAI rejects the key: use a developer API key with credits, not a ChatGPT password.
- Import/Apply says the size does not match: the PNG must be the same pixel size as the canvas. The plugin will not stretch or crop.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Plugin code lives in `ai_art_assistant/`. Krita discovers it through `ai_art_assistant.desktop`.

## License

MIT. See [LICENSE](LICENSE).
