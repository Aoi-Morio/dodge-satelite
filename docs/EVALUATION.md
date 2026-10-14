# Evaluation plan / 実写評価計画

No on-sky observations have been collected for v0.1.0. Claims below are proposed
measurements, not accomplished accuracy results.

1. Save raw GP CSV, acquisition time, file hash, software/dependency versions,
   site, full input profile and UTC clock synchronization evidence for every run.
   Do not use today's orbital elements as historical truth.
2. Record real fixed-target exposures with UTC start/end, camera timing latency,
   focal length, sensor dimensions, plate-solved field center/orientation and
   observing conditions. Keep raw FITS frames separately; v0.1 does not read them.
3. Label satellite trails independently of predictions. Record uncertain trails,
   aircraft/meteors and edge-of-frame cases separately. Where possible identify
   the satellite without forcing a match to the app's catalog.
4. Compare predictions with measured trail timing and positions. Report timing
   and angular residual distributions, precision/recall, false-negative rate,
   false-positive rate, unused observing time and saved usable integration.
   Separate all-trail recall from recall conditional on a known cataloged satellite.
5. Compare a baseline cadence with the proposed avoidance cadence using matched
   windows and documented weather/target selection. Predicted reduction is not
   an observed improvement; do not infer causality from unmatched sessions.
6. Stratify by orbital epoch distance (e.g. <1, 1–3, 3–7, >7 days), altitude,
   field size, sampling step, satellite speed, shadow boundary and constellation.
   Include near-pole, RA wrap, horizon, twilight and very narrow fields.
7. Test multiple margins and steps on held-out sessions. Choose thresholds from
   evidence, publish failures and uncertainty, and avoid presenting a small
   hand-picked sample as a universal bound.

Proposed initial collection: at least three observing nights, two focal lengths,
and enough labeled crossings to report counts and uncertainty for every metric.
The required sample size for a claimed false-negative limit must be justified
before making that claim. A catalog with no observed crossing cannot establish
that the software is accurate.

日本語要約: 元の軌道CSV・時刻同期・実写FITS・プレートソルブ結果を保管し、
予測とは独立に軌跡を分類します。見逃し・過検出・時刻と角度の残差・有効積算時間を
比較し、元期差・画角・高度・薄明別に分けて評価します。現段階では実写精度も改善率も
未測定です。
