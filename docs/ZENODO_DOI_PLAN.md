# Zenodo DOI Plan

This document describes the recommended workflow to publish **RingSentry** on Zenodo and bind the software DOI as strongly as possible to the real researcher identity **Delun Gong**.

## Short answer

Yes. The DOI can be tied much more strongly to the real person than to a GitHub username, but only if the release metadata contains:

- the real creator name: `Delun Gong`
- the ORCID iD
- optionally the institutional affiliation

Without the ORCID iD in the release metadata, the DOI still exists, but the identity link is weaker.

## Official basis

Zenodo and ORCID currently support the following official pieces of the workflow:

- Zenodo can link both **GitHub** and **ORCID** accounts:  
  https://help.zenodo.org/docs/profile/linking-accounts/
- Zenodo can automatically archive GitHub releases after the repository is enabled:  
  https://help.zenodo.org/docs/github/enable-repository/  
  https://help.zenodo.org/docs/github/archive-software/github-upload/
- Zenodo automatically registers a DOI when a record is published:  
  https://help.zenodo.org/docs/get-started/quickstart/  
  https://help.zenodo.org/docs/deposit/about-records/
- Zenodo can read repository metadata from `CITATION.cff`, but if `.zenodo.json` is present, Zenodo uses `.zenodo.json` and ignores `CITATION.cff` for GitHub release archiving:  
  https://help.zenodo.org/docs/github/describe-software/citation-file/  
  https://help.zenodo.org/docs/github/describe-software/zenodo-json/
- ORCID allows works to be added using a DOI, and DataCite can auto-update ORCID when the DOI metadata includes your ORCID iD and auto-update is enabled:  
  https://support.orcid.org/hc/en-us/articles/360022298153-Add-works-using-an-identifier  
  https://support.orcid.org/hc/en-us/articles/360006894594-Auto-updates-in-third-party-systems-DataCite

## Recommended identity-binding strategy

For academic credit, the best setup is:

1. Your Zenodo account is linked to your ORCID account.
2. The Zenodo release metadata lists the creator as **Delun Gong**, not only `D-sudoasd`.
3. The metadata includes your **ORCID iD**.
4. The metadata also includes your **affiliation** if you want institutional visibility in citations and discovery systems.
5. After publication, the DOI is imported into ORCID or allowed to sync automatically via DataCite.

## Why `.zenodo.json` is retained

The repository contains both `CITATION.cff`, for citation metadata and GitHub's citation display, and `.zenodo.json`, for Zenodo-specific release metadata.

For Zenodo archiving, however, `.zenodo.json` is the more precise file when you need stronger metadata control, because it supports Zenodo-specific fields and takes precedence over `CITATION.cff`.

This is the file that should carry your real-name creator metadata for archival releases.

## Current `.zenodo.json` structure

The root-level `.zenodo.json` currently records:

```json
{
  "title": "RingSentry",
  "version": "7.0.0",
  "upload_type": "software",
  "access_right": "open",
  "license": "mit",
  "language": "eng",
  "creators": [
    {
      "name": "Gong, Delun",
      "orcid": "0000-0001-7877-7707",
      "affiliation": "Institute of Metal Research, Chinese Academy of Sciences, Shenyang, People's Republic of China",
      "type": "ProjectMember"
    }
  ],
  "keywords": [
    "2D diffraction",
    "SAXS",
    "WAXS",
    "SXRD",
    "GIWAXS",
    "image preprocessing"
  ]
}
```

These values agree with `CITATION.cff` and the JOSS paper draft. They should be confirmed by the author immediately before an archival release.

## Recommended release workflow

### One-time setup

1. Create or log in to Zenodo.
2. Link both GitHub and ORCID in Zenodo.
3. Enable this repository in Zenodo's GitHub integration.

### Before the next archival release

1. Update `CHANGELOG.md`.
2. Update `CITATION.cff`.
3. Add or update `.zenodo.json` with:
   - real name
   - ORCID
   - affiliation
   - release version
4. Create a normal GitHub release for the next archival version, for example `v7.0.0` or later.

### After the GitHub release

1. Wait for Zenodo to ingest the release.
2. Open the new Zenodo software record.
3. Verify:
   - title is correct
   - creator is shown as `Delun Gong`
   - ORCID is present
   - affiliation is present if desired
   - DOI resolves correctly
4. Add the DOI to your ORCID record if it does not appear automatically.

## Practical recommendation for your repository

For your academic use case, the most defensible target is:

- GitHub identity: `D-sudoasd`
- citation identity: `Delun Gong`
- archival identity in Zenodo: `Delun Gong + ORCID + affiliation`
- researcher profile identity: ORCID record containing the DOI

That combination is much stronger for authorship attribution, software citation, academic CV use, and grant / paper reporting than using only a GitHub username.

## Current repository status

The current source metadata identify:

- creator name: `Delun Gong`
- ORCID iD: `0000-0001-7877-7707`
- affiliation: `Institute of Metal Research, Chinese Academy of Sciences, Shenyang, People's Republic of China`
- source version: `7.0.0`
- latest public tag and version archive: `v6.0.1`
- concept DOI: `10.5281/zenodo.19602728`

The account-linking and repository-enablement state cannot be inferred from local files. Before the next archival release, confirm those external settings and keep `.zenodo.json`, `CITATION.cff`, the tag, the release, and the archived source version aligned.

## What to do next in practice

1. Link your **GitHub** and **ORCID** accounts inside Zenodo.
2. Enable this repository in the Zenodo GitHub integration.
3. Before the next archival release, bump the version in:
   - `CHANGELOG.md`
   - `CITATION.cff`
   - `.zenodo.json`
4. Create a new GitHub release for the next archival version, for example `v7.0.0` or later.
5. Wait for Zenodo to archive it and mint the DOI.
6. Verify in the Zenodo record that:
   - creator is `Delun Gong`
   - ORCID is shown correctly
   - affiliation is shown correctly
7. Add the DOI to ORCID if it does not sync automatically.

## Recommendation on public contact details

For DOI binding and software citation, it is usually sufficient to publish:

- real name
- ORCID
- affiliation

It is generally **not necessary** to include a telephone number or direct email address in Zenodo archival metadata unless you explicitly want them to be permanently public.
