# Farm photos on the map

Geotagged photos show as dark markers on the map; clicking one opens the photo with its
caption and date. The site is public, so anything added here is visible to anyone,
along with where it was taken.

## Add photos

1. Export from Photos with the location kept:
   - Mac: **File → Export → Export Unmodified Original**, or **Export N Photos…** with
     **Location information** (and **Title, Caption, Keywords**) ticked.
   - iPhone: Share → **Options** → turn **Location** on, then AirDrop or **Save to Files**.
   - Emailing or messaging photos usually strips the location.
2. Drop them into this folder (subfolders are fine, e.g. `photos/2026-10-28/`).
   JPEG, HEIC and PNG all work.
3. Optionally add captions in [captions.txt](captions.txt). A caption typed in Photos
   is used if there's no line for the photo here.
4. Build the web copies and commit them:

   ```bash
   pip install -r photos/requirements.txt
   python photos/build.py
   git add web/photos && git commit -m "Add farm photos" && git push
   ```

The build prints any photo it skipped for having no location. Place those by hand with
`@ lat, lon` at the end of their line in `captions.txt`; you can get the numbers by
right-clicking the spot in Google Maps.

## What gets published

Only the web copies in `web/photos/` (1600 px, plus 400 px thumbnails) and
`web/photos/photos.geojson`. They are saved with no metadata: no camera details, and no
GPS beyond the map position. The originals in this folder are git-ignored, so keep them
somewhere else too. Deleting an original and re-running the build removes it from the map.

HEIC needs `pillow-heif`; if it won't install, the build falls back to macOS's `sips`.
