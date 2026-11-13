# Data notice

This repository publishes a **names-only index** for MTG Arena card names. It is
an unofficial fan project and is not affiliated with or endorsed by Wizards of
the Coast, Hasbro, or any game platform.

## Rights

- MTG Arena, Magic: The Gathering, card names, localized text, and related marks
  belong to Wizards of the Coast and their respective rights holders.
- The Chinese names are taken from the Arena client localization and/or
  community-reviewed maintenance data. They are not independently verified as
  official translations for every row.
- This project does not grant any license to the data. Public availability does
  not mean the data is MIT-licensed, public domain, or free to redistribute.
  The MIT license in this repository applies to code only.

## Scope

The dataset contains only:

- Arena `GrpId` / `TitleId`
- English and Simplified Chinese **card titles**
- minimal identity fields (set, collector number, primary/token/face flags)
- upstream status/source labels

It does **not** contain rules text, flavor text, UI strings, source evidence,
game files, fonts, account data, or private keys.

## Use

- Fan tools may use the index to display card names.
- Do not present it as official, complete, or verified.
- Do not use it to redistribute game text, game files, or a full localization
  database.
- If you build a product on it, keep a fallback for missing names and pin a
  release version.

## Takedown / corrections

If you are a rights holder and want a row or the dataset removed, open an issue
or contact the maintainer through GitHub. Corrections with a source are welcome.
