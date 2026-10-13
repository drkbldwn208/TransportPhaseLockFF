# Selecting a PYNQ overlay revision

Run these commands inside the repository clone on your PC or board. Fetching
updates remote history and tags; it does not change your checked-out files.

```bash
git fetch origin --tags
git log origin/FreqLocks --date=short --format='%H  %ad  %s' -- pynq_overlays/latest
git tag --sort=-creatordate
```

The log is restricted to commits that changed the downloadable overlay. A source
change alone does not prove that a new bitstream was built. Choose a commit with
the desired matched bit/HWH and helpers. Check a candidate before downloading:

```bash
git show --stat COMMIT_SHA -- pynq_overlays/latest python_scripts
git rev-parse COMMIT_SHA_OR_TAG^{commit}
```

Copy the resulting full 40-character hash. No checkout or push is needed to
download an existing commit. The downloader prompts for a token with repository
read access, downloads both files into a temporary directory, and only replaces
the existing pair after both downloads succeed:

```bash
bash scripts/download_overlay.sh FULL_40_CHARACTER_COMMIT_SHA ./overlays
```

On the board, use the same directory that your notebook's `Overlay(...)` points
to. The script writes `overlay_commit.txt` beside the pair. Downloading files does
not program the FPGA; calling `Overlay(...)` with download enabled does, and
interrupts running feedback loops. Refresh matching Python helpers separately.

The URL change from a branch to a commit is simply:

```bash
REF="FULL_40_CHARACTER_COMMIT_SHA"
BASE_URL="https://raw.githubusercontent.com/drkbldwn208/TransportPhaseLockFF/$REF/pynq_overlays/latest"
```

Do not leave the placeholder text as the value of `REF`. A full SHA prevents
the branch from advancing between the bit and HWH downloads. Do not store a
GitHub token in a script or repository. Revoke any token exposed in pasted text.

## Intensity-servo regression and rollback

- `7758dff2d875dbf4ad56dcc0e43feec06226b2f6` (A6): saved HWH connects ADC224/1
  data/valid to `iq_split_0`. This is an older feature set requiring A6 helpers.
- The original `build/laser_pll_overlay_A7.zip`: correct intensity connection,
  with matched original A7 hardware/helpers; it predates the new RF phase FRA.
- `9fa9cb6b500feceac85c6096256d49be23b36866` (A8) and
  `f41d4fd77e3a8edfc34bd2eab7d0b36e472eb22b` (initial R7 RF-FRA): incorrect
  intensity ADC connection. An apparently connected BD interface is overridden
  by orphan scalar data/valid nets. These are unsuitable intensity-servo fallbacks.
- The R7 repair removes those orphan nets and checks actual generated HWH and
  Verilog connectivity before synthesis and packaging. Use the rebuilt release's
  `verification.json` field `intensity_servo_restored.status == "pass"` to identify
  the corrected package. The A7 register version itself is unchanged.

There were no local tags when this repair started. Once you have committed and
pushed a verified release, an optional annotated tag makes it easier to find:

```bash
git tag -a r7-intensity-restored VERIFIED_COMMIT_SHA -m "R7 FRA with intensity ADC restored"
git push origin r7-intensity-restored
```

Tagging is optional. This example does not automatically commit or push changes.

References: [Git log](https://git-scm.com/docs/git-log),
[GitHub commit-pinned links](https://docs.github.com/en/repositories/working-with-files/using-files/getting-permanent-links-to-files).
