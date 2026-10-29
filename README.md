# Krita AI Art Assistant

A **Krita Python plugin** for artist-controlled image editing. You sketch or paint in Krita, optionally select a region, type an instruction, and request an AI edit. The result comes back as a **new layer**. Original layers are not overwritten.

This is a public-source production tool, not a commercial product. Recruiters do not need to install Krita to read this page. A walkthrough video will be linked here when it exists.

**Pinned Krita version:** 5.3.4.1 for Windows (`C:\Program Files\Krita (x64)\`).

## How it is supposed to work

1. Capture the **visible canvas** (what Krita is showing, not a screenshot and not only one layer).
2. Capture the current **selection** as a full-size stencil when you are editing part of the image.
3. **Composite** so applied pixels stay inside that selection, even if the model changes more than it should (later version).
4. Insert the result as a **new undoable layer**.

```
sketch in Krita -> panel -> visible picture + selection stencil
                 -> OpenAI Image Edit
                 -> preview, then new layer if you apply
```

Generate uploads the visible canvas (and mask, if any) to OpenAI. That uses **API credits**, not a ChatGPT Plus subscription.

## Implemented / Not yet

**Implemented (Phase 2)**

- Krita docker named **AI Art Assistant**
- Document name/size and selection status
- Export visible canvas / selection stencil; import PNG as a new layer
- OpenAI Image Edit (`gpt-image-2.5-flare`): one image per Generate click
- API key in Windows Credential Manager (session-only fallback)
- Candidate preview, then Apply as new layer / Discard / Retry
- Automatic tests for size, stencil coverage, mask inversion, and fake HTTP (no paid calls)

**Not yet**

- Clipping the AI result to the selection (the mask is guidance only for now)
- Spend caps / request ledger
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
- Original layers still there after Apply; Undo removes the new layer

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
