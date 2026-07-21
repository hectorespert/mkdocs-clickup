## 1. Preprocess: stop removing content images/SVGs

- [x] 1.1 Remove the blanket `tag.name in {"img", "svg"}` rule from `_to_remove()` in `preprocess.py`
- [x] 1.2 Confirm the existing `"twemoji" in classes` check still removes decorative emoji/`:material-*:` icon glyphs (both `<svg>` and `<img>` shapes) now that the blanket rule is gone
- [x] 1.3 Confirm the `tag.name == "a" and tag.img and _to_remove(tag.img)` rule still behaves correctly now that a plain `<img>` no longer self-matches (a link wrapping a real content image should survive; a link wrapping a decorative twemoji icon should still be removed)

## 2. Resolve and embed image/SVG sources as data URIs

- [x] 2.1 Add a resolution step (in `_generate_page_markdown` or a new helper) that, for each `<img>` tag: leaves already-absolute `src` values (`http://`, `https://`, existing `data:`) untouched; for a local/relative `src`, resolves it to the file on disk and reads its bytes
- [x] 2.2 Base64-encode the resolved bytes and rewrite `src` to `data:<mime>;base64,<...>`, using `mimetypes.guess_type` (or equivalent) for the MIME type
- [x] 2.3 For a preserved inline `<svg>` (survived step 1), serialize its own markup and rewrite it into an equivalent Markdown image reference with `data:image/svg+xml;base64,<...>`
- [x] 2.4 Raise a build-aborting error (consistent with the capability's existing failure philosophy) when a local image/SVG source can't be resolved or read, identifying the page and the broken reference

## 3. Tests

- [x] 3.1 `<img>` survives `autoclean` regardless of its enabled/disabled value
- [x] 3.2 Content `<svg>` (no `twemoji` class) survives `autoclean`
- [x] 3.3 Decorative `<svg class="twemoji">` and `<img class="twemoji">` are still removed by `autoclean`
- [x] 3.4 A local `<img src>` is rewritten to a `data:` URI with the correct MIME type and base64 payload
- [x] 3.5 A content `<svg>` is rewritten to a `data:image/svg+xml;base64,...` Markdown image reference
- [x] 3.6 An already-absolute `<img src>` (e.g. `https://...`) is left unchanged
- [x] 3.7 An unreadable/missing local image raises a build error naming the page and the broken reference
- [x] 3.8 Embedding works with `site_url` unset (no dependency introduced)

## 4. Documentation

- [x] 4.1 Update the README's "ClickUp API research" section with the confirmed findings: no attachment/upload endpoint exists for Docs/Pages; images work via a Markdown `data:` URI or absolute URL in `content`, live-verified (API round-trip + visual check) against a real workspace
- [x] 4.2 Note the still-unresolved `content` size-limit risk as a known limitation for image-heavy pages, pending a future check against a disposable/sandbox workspace
