# Zenodo DOI Plan

This document describes the recommended workflow to publish **2D Diffraction Ring Preprocessor** on Zenodo and bind the software DOI as strongly as possible to the real researcher identity **Delun Gong**.

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

## Why `.zenodo.json` is the key next step

Right now the repository has a `CITATION.cff`, which is good for GitHub citation display.

For Zenodo archiving, however, `.zenodo.json` is the more precise file when you need stronger metadata control, because it supports Zenodo-specific fields and takes precedence over `CITATION.cff`.

This is the file that should carry your real-name creator metadata for archival releases.

## Recommended `.zenodo.json` structure

Once your ORCID iD is available, add a root-level file named `.zenodo.json` like this:

```json
{
  "title": "2D Diffraction Ring Preprocessor",
  "version": "6.0.1",
  "upload_type": "software",
  "access_right": "open",
  "license": "mit",
  "language": "eng",
  "creators": [
    {
      "name": "Gong, Delun",
      "orcid": "0000-0000-0000-0000",
      "affiliation": "Your Institution",
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

Use your real ORCID iD and real affiliation. Do not publish placeholder values.

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
4. Create a normal GitHub release for the next archival version, for example `v6.0.1` or later.

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

The repository metadata can now be prepared as:

- creator name: `Delun Gong`
- ORCID iD: `0000-0001-7877-7707`
- affiliation: `Institute of Metal Research (IMR), Chinese Academy of Sciences (CAS)`

The recommended next repository step is to keep `.zenodo.json` and `CITATION.cff` aligned before the next archival release.

## What to do next in practice

1. Link your **GitHub** and **ORCID** accounts inside Zenodo.
2. Enable this repository in the Zenodo GitHub integration.
3. Before the next archival release, bump the version in:
   - `CHANGELOG.md`
   - `CITATION.cff`
   - `.zenodo.json`
4. Create a new GitHub release for the next archival version, for example `v6.0.1` or later.
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
