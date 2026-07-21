# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

<!-- insertion marker -->
## [1.0.0](https://github.com/hectorespert/mkdocs-clickup/releases/tag/1.0.0) - 2026-07-21

<small>[Compare with 0.5.0](https://github.com/hectorespert/mkdocs-clickup/compare/8968edfb0e66c56e60072f0da74d37c2dc78d8ef...1.0.0)</small>

First release of the fork under its own name: the plugin now actually publishes to ClickUp Pages (the previous `0.x` versions were the `mkdocs-llmstxt` ancestor this project started from, and are kept below for history).

### Features

- Embed images, content SVGs, and Mermaid diagrams as inline images ([8695060](https://github.com/hectorespert/mkdocs-clickup/commit/86950603389a3dae277c56185cb2f4565f212948) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>
- Prepend a do-not-edit notice to every published ClickUp page ([c5dcd48](https://github.com/hectorespert/mkdocs-clickup/commit/c5dcd48565c2f4d86543cbd21f7831faffc83d30) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>
- Retry transient ClickUp API failures when publishing ([d144f79](https://github.com/hectorespert/mkdocs-clickup/commit/d144f7982358569ad1243054ce6bbd58359c0573) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>
- Mirror MkDocs navigation hierarchy as nested ClickUp pages ([cfea295](https://github.com/hectorespert/mkdocs-clickup/commit/cfea295deb070cba04af69fd5c4b4963b70133dc) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>
- Publish idempotently, matching pages by sub_title ([0179735](https://github.com/hectorespert/mkdocs-clickup/commit/017973557d51a22a48ad959590224b7b119b1451) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>
- Publish MkDocs pages to ClickUp Docs ([ac39bcc](https://github.com/hectorespert/mkdocs-clickup/commit/ac39bcc58d64b69ea711493a0e01adeed61e9f67) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>

### Bug Fixes

- Require resvg-py>=0.3.3, 0.3.2 rejects a float zoom argument ([23d0810](https://github.com/hectorespert/mkdocs-clickup/commit/23d0810083795c9a255ca00d5b8c7c1be0495879) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>
- Silence pre-existing mypy error in gen_credits.py ([1174297](https://github.com/hectorespert/mkdocs-clickup/commit/1174297196da0c1c62fe07076748dbc7a387bb26) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>

### Code Refactoring

- Bootstrap package rename and strip llms.txt-specific behavior ([01b9e6d](https://github.com/hectorespert/mkdocs-clickup/commit/01b9e6d024beb3504554b382d38f7e9f403b5dac) by Hector Espert). Assisted-By: Claude Sonnet 5 <noreply@anthropic.com>

## [0.5.0](https://github.com/pawamoy/mkdocs-llmstxt/releases/tag/0.5.0) - 2025-11-20

<small>[Compare with 0.4.0](https://github.com/pawamoy/mkdocs-llmstxt/compare/0.4.0...0.5.0)</small>

### Features

- Resolve relative links to absolute ones, link to generated Markdown files ([52e0318](https://github.com/pawamoy/mkdocs-llmstxt/commit/52e0318be1965494a8d3bdc854a25e02e6f71cb8) by 권세인). [Issue-22](https://github.com/pawamoy/mkdocs-llmstxt/issues/22), [PR-26](https://github.com/pawamoy/mkdocs-llmstxt/pull/26), Co-authored-by: Timothée Mazzucotelli <dev@pawamoy.fr>

## [0.4.0](https://github.com/pawamoy/mkdocs-llmstxt/releases/tag/0.4.0) - 2025-10-03

<small>[Compare with 0.3.2](https://github.com/pawamoy/mkdocs-llmstxt/compare/0.3.2...0.4.0)</small>

### Features

- Add `base_url` config option ([718b0bc](https://github.com/pawamoy/mkdocs-llmstxt/commit/718b0bcc0183d6c64a57dc2efee93552d170e9e3) by Jo Stichbury). [PR-25](https://github.com/pawamoy/mkdocs-llmstxt/pull/25)

## [0.3.2](https://github.com/pawamoy/mkdocs-llmstxt/releases/tag/0.3.2) - 2025-09-19

<small>[Compare with 0.3.1](https://github.com/pawamoy/mkdocs-llmstxt/compare/0.3.1...0.3.2)</small>

### Code Refactoring

- Skip files not found, log warning (don't crash) ([8407d93](https://github.com/pawamoy/mkdocs-llmstxt/commit/8407d9316960d7f4713d7ab0d7c5aeb8d2ced7e8) by Timothée Mazzucotelli). [Issue-23](https://github.com/pawamoy/mkdocs-llmstxt/issues/23)

## [0.3.1](https://github.com/pawamoy/mkdocs-llmstxt/releases/tag/0.3.1) - 2025-08-05

<small>[Compare with 0.3.0](https://github.com/pawamoy/mkdocs-llmstxt/compare/0.3.0...0.3.1)</small>

### Bug Fixes

- Preserve user-defined ordering of pages ([1359e25](https://github.com/pawamoy/mkdocs-llmstxt/commit/1359e250e675f7742d18f9641136fccc26199773) by Timothée Mazzucotelli). [Issue-21](https://github.com/pawamoy/mkdocs-llmstxt/issues/21)

## [0.3.0](https://github.com/pawamoy/mkdocs-llmstxt/releases/tag/0.3.0) - 2025-07-14

<small>[Compare with 0.2.0](https://github.com/pawamoy/mkdocs-llmstxt/compare/0.2.0...0.3.0)</small>

### Features

- Support file descriptions ([33f64b3](https://github.com/pawamoy/mkdocs-llmstxt/commit/33f64b306199218dbb34cd796e59113388a6c26c) by Logan). [Issue-6](https://github.com/pawamoy/mkdocs-llmstxt/issues/6), [PR-8](https://github.com/pawamoy/mkdocs-llmstxt/pull/8), Co-authored-by: Timothée Mazzucotelli <dev@pawamoy.fr>

### Bug Fixes

- Support formatting Markdown tables ([f1fc875](https://github.com/pawamoy/mkdocs-llmstxt/commit/f1fc8757dcab95af7b645331ddc5f1f01888bc88) by Timothée Mazzucotelli). [Issue-13](https://github.com/pawamoy/mkdocs-llmstxt/issues/13)

## [0.2.0](https://github.com/pawamoy/mkdocs-llmstxt/releases/tag/0.2.0) - 2025-04-08

<small>[Compare with 0.1.0](https://github.com/pawamoy/mkdocs-llmstxt/compare/0.1.0...0.2.0)</small>

### Breaking changes

The configuration options changed, check the docs.

### Code Refactoring

- Actually generate llms.txt file as per the specification ([1f0e417](https://github.com/pawamoy/mkdocs-llmstxt/commit/1f0e417855240a8aab07c3cbcfeb8b8251c1ffb4) by Victorien). [Issue-1](https://github.com/pawamoy/mkdocs-llmstxt/issues/1), [PR-4](https://github.com/pawamoy/mkdocs-llmstxt/pull/4), Co-authored-by: Timothée Mazzucotelli <dev@pawamoy.fr>
- Use public/internal API layout ([4dff69d](https://github.com/pawamoy/mkdocs-llmstxt/commit/4dff69db35d895e8d04535e75a2e08d0a219dc88) by Timothée Mazzucotelli).

## [0.1.0](https://github.com/pawamoy/mkdocs-llmstxt/releases/tag/0.1.0) - 2025-01-14

<small>[Compare with first commit](https://github.com/pawamoy/mkdocs-llmstxt/compare/6f25f9610f2fbccdbaf3f8960bc058dc3d2a8c1e...0.1.0)</small>

### Features

- Implement first version ([e4d9c5e](https://github.com/pawamoy/mkdocs-llmstxt/commit/e4d9c5e76fa2dce9c190fdb1bb6bb873d1f6622e) by Timothée Mazzucotelli).
- Initial commit ([6f25f96](https://github.com/pawamoy/mkdocs-llmstxt/commit/6f25f9610f2fbccdbaf3f8960bc058dc3d2a8c1e) by Timothée Mazzucotelli).
