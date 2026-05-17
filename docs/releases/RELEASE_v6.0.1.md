# v6.0.1 - Zenodo-ready metadata release

Recommended GitHub release title:

`v6.0.1 - Zenodo-ready metadata release`

## Summary

This release prepares the repository for Zenodo archival publication and stronger academic attribution of the software to **Delun Gong** through real-name citation metadata, ORCID-linked metadata, and release documentation improvements.

本版本用于将仓库调整到适合 Zenodo 归档发布的状态，并通过实名引用元数据、ORCID 关联元数据和发布文档增强，把软件成果更明确地归属于 **Delun Gong**。

## Highlights

- Added ORCID-linked repository citation metadata
- Added `.zenodo.json` for Zenodo archival metadata control
- Added contribution and security policy documents
- Improved GitHub README landing page for citation and release visibility
- Added local publish helper scripts for future maintenance workflow

## Included in v6.0.1

- `CITATION.cff` now includes:
  - `Delun Gong`
  - ORCID `0000-0001-7877-7707`
  - affiliation `Institute of Metal Research (IMR), Chinese Academy of Sciences (CAS)`
- `.zenodo.json` added for Zenodo release ingestion
- `CONTRIBUTING.md` and `SECURITY.md` added
- `docs/ZENODO_DOI_PLAN.md` added for DOI workflow documentation
- README updated to improve public presentation and release navigation

## Why this release matters

This release is intended to trigger Zenodo archival capture after repository linking, so that the resulting DOI is associated with stronger author metadata and can be connected to the research identity of **Delun Gong** and ORCID.

## Installation

```bash
pip install -r requirements.txt
python main.py
```

Standalone Q calculator:

```bash
python tools/q_calculator_standalone.py
```

## Notes

- Platform focus: Windows desktop workflow
- Optional dependency: `fabio` for CBF / ADSC / Bruker support
- `config.json` stores local user settings and is intentionally not tracked
- This release is especially intended for Zenodo DOI generation after GitHub-Zenodo integration is enabled

## Repository

https://github.com/D-sudoasd/2d-image-processor
