# Model Result Contract

The data package is a model input contract. The application does not train a model or choose an action threshold. A new prediction must be saved in an independent versioned directory, for example `research/model-name_date/predictions.csv`, and uploaded through the page. `artifacts/predictions.csv` is the frozen main-experiment file and must not be overwritten. Temporary research directories are not part of the engineering package; a delivered experiment needs its own version and manifest.

## Required fields

| Field | Requirement |
| --- | --- |
| `sample_id` | Must exist in the current `samples.csv` |
| `method` | Non-empty method name |
| `probability` | Finite numeric value from 0 to 1, not missing |
| `model_version` | Non-empty, traceable model version |
| `dataset_version` | Exactly matches `reports/data_quality.json` |
| `experiment_kind` | Matches the sample's experiment kind |
| `event_threshold_mm` | Positive threshold used by this contract; target is 24-hour accumulation reaching it |

The combination `sample_id + method + model_version` must be unique. A method may cover only part of the samples, but the material must report its coverage. The input `split` starts as `unassigned`; the experiment owner must fix a time split before training and retain model and configuration files.

Passing schema validation means only that rows can be joined correctly. It does not prove that the model is valid, that probabilities are trustworthy, or that independent evaluation has passed. The app does not create accuracy or avoided-loss claims from an uploaded file.

Offline fixed-lead experiments, hindcasts, and real decision replays must remain distinct. When publication time is not verified, a result cannot be rewritten as an operational score with a claimed lead time.
