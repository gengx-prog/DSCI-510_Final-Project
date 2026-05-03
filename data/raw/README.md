# Raw Data Notes

This folder contains the raw source files that are small enough to include in GitHub.

The full ACLED raw exports are intentionally not committed because they exceed GitHub's normal file-size limit:

- `acled_raw.csv`
- `acled_supplement.csv`

To recreate the ACLED raw data, set the ACLED credentials described in the root `README.md` and run:

```bash
python src/get_data.py --source acled
```

