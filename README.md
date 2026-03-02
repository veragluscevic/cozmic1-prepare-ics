## COZMIC1-template-files/

Reference files from COZMIC I (arXiv:2410.03635).

- **CDM_class_sync_tk.dat** — Raw CLASS synchronous-gauge CDM transfer function output for COZMIC I cosmology (h=0.7, Omega_m=0.286, Omega_b=0.049, sigma_8=0.82, n_s=0.96). Used as the CDM reference by `plot_transfer_from_sim_table.py` and `analyze_pk.py`.
- **test_CDM.dat** — Same CDM run converted to CAMB 13-column format via `class_to_camb.py`. Used as a validation reference by `test_conversion.py`.
- **minimal_syncronous.ini** — CLASS input template for synchronous-gauge runs. Used by `prepare-transfers.sh`, `generate_all_inis_from_sim-table.py`, and `analyze_pk.py` to generate per-model ini files.
- **minimal_newtonian.ini** — CLASS input template for Newtonian-gauge runs.
- **data_tk/** — Original CAMB-formatted transfer functions from Rui. Used by `test_conversion.py` as the reference CAMB output for validating `class_to_camb.py` conversions.

## Tests

- **`test_conversion.py`** — Compares a CAMB-converted transfer function against Rui's original CAMB output, column by column. Prints PASSED if `(|T_camb| - |T_class|)^2 / T_cdm^2 < 0.01` for all k, otherwise warns to check plots. You may want to run it for i=1,2,6,10,11, for a complete set of tests. Example:
  ```
  python test_conversion.py -i 1
  python test_conversion.py --class-file transfers/camb_n2_1e-2GeV_7.1e-24_tk.dat --camb-file COZMIC1-template-files/data_tk/idm_n2_1e-2GeV_envelope_z99_Tk.dat -i 1 -o plots/test_n2_envelope_i1.png
  ```
- **`plot_transfer_from_sim_table.py`** — Plots `(d_dmeff / d_cdm)^2` vs `k` for a given `(n, m)`, reading sigma values from `sim-table.dat`. Shows halfmode, midpoint (optional), and envelope curves alongside the WDM transfer function. Use `--output-dir` to specify a custom location for CLASS transfer files. Example:
  ```
  python plot_transfer_from_sim_table.py -n 2 -m 1e-2
  python plot_transfer_from_sim_table.py -n 4 -m all --no-midpoint -s
  ```
