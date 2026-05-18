# Analytical Skill: Clustering Algorithms

**Loaded by:** Pattern Discoverer.
**Purpose:** Identify natural groupings in unlabeled data. Choose the appropriate algorithm for the data shape and the analytical question, validate that the clusters are real rather than imposed, and interpret cluster meaning in business terms.

## Algorithm selection

| Data shape / question | Algorithm | Notes |
|---|---|---|
| Compact, roughly spherical clusters of similar size | **k-means** | Fast; requires choosing *k* in advance; sensitive to feature scaling. Standardize features first. |
| Clusters of arbitrary shape; varying density | **DBSCAN** | No need to choose *k*; naturally identifies outliers as a "noise" class; sensitive to `eps` and `min_samples`. Good when outlier characterization matters. |
| Hierarchical structure desired (e.g., nested account tiers) | **Agglomerative hierarchical** (Ward, complete, or average linkage) | Produces a dendrogram; *k* can be chosen post-hoc. Computationally heavier on large *n*. |
| Mixed continuous and categorical features | **k-prototypes** or hierarchical with Gower distance | k-means assumes continuous features only. |
| Latent-class style structure on categorical or mixed data | **Gaussian mixture model (GMM)** | Soft assignment; works on continuous; relaxes the equal-size, spherical assumptions of k-means. |
| Time-series shapes | **DTW-based clustering** | Requires distance computation on aligned sequences — typically the [cohort-analysis.md](cohort-analysis.md) territory. |

For typical entity segmentation in our CPG functional domains *(Examples: sales — account or SKU segmentation; supply chain — DC clustering by operating profile; operations — production-line grouping by changeover signature; trade marketing — campaign segmentation)*, **k-means or k-prototypes** are usually the right defaults. For outlier-rich data — when many entities may not belong to any tidy cluster — **DBSCAN** is more honest because it labels those points as noise rather than forcing them into the nearest centroid.

## Required steps and reporting

1. **Feature preparation**: standardize continuous features (z-score on roughly-normal; robust-scaler — median/IQR — on skewed). Encode categoricals appropriately for the chosen algorithm. Record the preparation steps as part of the artifact.

2. **Choosing *k* (or `eps`)**:
   - For k-means and hierarchical: compute the **silhouette score** across a range of *k* (typically 2–10); also compute the **gap statistic** or **elbow** of within-cluster sum of squares. Report all of these; do not select *k* on one metric in isolation.
   - For DBSCAN: use a *k*-distance plot to choose `eps`; report the chosen `eps` and the resulting noise fraction.
   - For GMM: use BIC across candidate *k* values; report BIC curve.

3. **Validation**:
   - Silhouette score per chosen *k* (range −1 to 1; ≥ 0.5 is strong, 0.25–0.5 moderate, < 0.25 weak).
   - Cluster stability via bootstrap or repeated runs with different seeds — clusters that re-form across runs are real; ones that don't are artifacts of initialization.
   - Cluster sizes — a "cluster" of 2 points out of 50,000 usually isn't one; flag as outlier rather than cluster.

4. **Characterization** — for each cluster, compute:
   - Size (count and percent of total).
   - Centroid (or medoid for robustness) on each feature.
   - The features that most distinguish the cluster from the population mean (effect-size ranking).
   - A short plain-language characterization tying back to the domain context (e.g., "high-velocity, low-promo-frequency accounts").

5. **Anti-cluster honesty** — if no *k* yields silhouette ≥ 0.25 and clusters are unstable across seeds, the right output is "no robust cluster structure found." Do not promote a noisy partition to a finding.

## Anti-patterns

- Choosing *k* to match a pre-existing intuition. The algorithm's job is to find what's there, not to confirm what was assumed.
- Running k-means on raw, un-standardized features. Distance is dominated by the largest-magnitude feature.
- Reporting cluster centroids without effect-size context — "cluster 2 has higher mean volume" is uninformative without "...by 1.2 SDs vs. the population, on a feature whose population variance is 8.4."
- Treating DBSCAN noise points as a cluster.
- Manufacturing a cluster narrative on a low-silhouette partition. If the structure isn't there, say so.

## Output-shape discipline

Code execution returns the cluster assignments **summary** — counts and centroids per cluster, validation statistics, and per-cluster characterization — never the per-row cluster label vector. The summary table is small; the row-level assignments stay in the sandbox and can be queried by filter expression if a downstream agent needs a specific cluster's members.
