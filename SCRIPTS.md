# Key Commands and Instructions

#############
# !!! Key files: sim-table.dat, prepare-transfers.sh, make_music_conf.py, and run_music.sh !!!

# Key results: output/, transfers/, configs/, ic/

# Before you begin, on the same level as this repo, do:
# git clone https://github.com/cosmo-sims/MUSIC2
# and then make the code in there so you can use it
# git clone git@github.com:kboddy/class_public.git class_dmeff_rui_used 
# git checkout dmeff
# and then make the code in there so you can use that version of CLASS
##############


## 0. sim-table.dat contains the IDM parameters for all planned and done runs. Do NOT change manually. 

## 1. Generate CLASS ini files

```bash
python generate_all_inis_from_sim_table.py
python generate_all_inis_from_sim_table.py --skip-done
```

Reads `sim-table.dat` and templates (`COZMIC1-files/minimal_syncronous.ini`, `COZMIC1-files/minimal_newtonian.ini`) to create ini files in `inis/`.

## 2. Run CLASS

```bash
python run_class_sim_table.py                                                   # defaults: inis/ -> output/
python run_class_sim_table.py --ini-dir inis --output-dir output          # custom directories
python run_class_sim_table.py --class-exe ../class_dmeff_rui_used/class                        # custom CLASS executable
```

Runs CLASS on all ini files in the specified directory, saves output and logs. Defaults: `--ini-dir inis/`, `--output-dir output/`, `--class-exe` from `CLASS_EXE` env var or `../class_dmeff_rui_used/class`.

## 3. Convert CLASS to CAMB format

```bash
python convert_all_transfers.py                                                 # defaults: output/ -> transfers/
python convert_all_transfers.py --class-tk-dir my_output --output-dir my_transfers # custom directories
```

Converts all CLASS output (sync + newt + background) to CAMB 13-column format.

Single file:

```bash
python class_to_camb.py output/n2_1e-2GeV_1.3e-25_sync_tk.dat output/n2_1e-2GeV_1.3e-25_newt_tk.dat output/n2_1e-2GeV_1.3e-25_sync_background.dat -o transfers/camb_n2_1e-2GeV_1.3e-25_tk.dat
```

## 4. Plot transfer functions

```bash
python plot_transfer_from_sim_table.py                                # defaults: n=2, m=1e-2
python plot_transfer_from_sim_table.py -n 4 -m 1e-4                   # specific (n, m)
python plot_transfer_from_sim_table.py -m all --no-midpoint            # all masses, skip midpoint
python plot_transfer_from_sim_table.py -m all --no-midpoint -s         # save to plots/
python plot_transfer_from_sim_table.py --mwdm 6.5                      # change WDM reference mass
```

## 5. Analyze transfer functions (compute k_hm)

```bash
python analyze_pk.py                                    # defaults: n=2, m=1e-2
python analyze_pk.py -m all -n 2                        # all masses for n=2
python analyze_pk.py -m all -n 4 --no-midpoint          # skip midpoint entries
python analyze_pk.py -m all --save-khm                  # write k_hm to sim-table.dat
python analyze_pk.py -m 1e-2 --plot -s                  # also plot and save figure
python analyze_pk.py -m all --save-khm --plot -s        # do everything
```

## 5b. Find halfmode/envelope sigma via CLASS

```bash
python analyze_pk.py -n 2 -m 1e-2 --recalculate-sigma                           # find sigma for one mass
python analyze_pk.py -n 2 -m all --recalculate-sigma                            # find sigma for all masses
python analyze_pk.py -n 2 -m 1e-2 --recalculate-sigma --khm-precision-percent 2  # tighter tolerance
python analyze_pk.py -n 2 -m 1e-2 --recalculate-sigma --mwdm 6.5               # match against different WDM
python analyze_pk.py -n 2 -m 1e-2 --recalculate-sigma --class-exe /path/to/class  # custom CLASS path
```

Checks existing sigma values against WDM criteria; only runs CLASS if match is bad. Updates `sim-table.dat` with new sigma and k_hm. Rows with `status=done` are never recalculated. Set `CLASS_EXE` env var for portability.

**Note:** the bisection search requires at least one non-nan sigma per (n, m) pair as a starting point. If both halfmode and envelope are nan, the script will error out.

## 5c. Batch run for all pending entries

```bash
./prepare-transfers.sh [--ini-dir DIR] [--class-tk-dir DIR] [--output-dir DIR] [--analyze]
```

Optional arguments:
- `--ini-dir DIR` — directory for ini files (default: `inis/`)
- `--class-tk-dir DIR` — directory for CLASS transfer output (default: `output/`)
- `--output-dir DIR` — directory for CAMB-converted transfers (default: `transfers/`)
- `--analyze` — also run `analyze_pk.py --recalculate-sigma --plot` for each (n, m) pair

For each pending (non-`done`) entry in `sim-table.dat`:

1. Generates any missing ini files in `--ini-dir`
2. Runs CLASS for entries with missing output files in `--class-tk-dir`
3. *(only with `--analyze`)* Runs `analyze_pk.py --recalculate-sigma --plot` for each (n, m) pair
4. Converts CLASS output to CAMB format in `--output-dir` (via `class_to_camb.py`)

## 6. Compare new converted CLASS transfers with the original CAMB output from Rui An; note that original CAMB-formatted transfers from Rui are in camb_class_conversion repo, within data_tk. 

```bash
python test_conversion.py                                                       # defaults: n2 envelope, column 1
python test_conversion.py --class-file <class_file> --camb-file <camb_file> -i <column_index>
python test_conversion.py --class-file transfers/camb_n2_1e-2GeV_7.1e-24_tk.dat --camb-file COZMIC1-files/data_tk/idm_n2_1e-2GeV_envelope_z99_Tk.dat -i 1 -o plots/test_n2_envelope_i1.png
```

## 7. Generate MUSIC configuration files for zoom-in ICs

```bash
python make_music_conf.py Halo004 transfers/camb_n2_1e-2GeV_1.3e-25_tk.dat
python make_music_conf.py Halo023 transfers/camb_n4_1e-1GeV_2.5e-20_tk.dat --wnoise-file my_wnoise.dat
python make_music_conf.py Halo004 --all-sim-table-transfers transfers
python make_music_conf.py Halo004 --all-sim-table-transfers transfers --sim-table sim-table.dat
```

`halo_name` is required. In single-file mode, provide one transfer file and it writes one config. In batch mode (`--all-sim-table-transfers <dir>`), it reads `sim-table.dat` and writes configs for transfer files in `<dir>` that correspond to non-`done`, non-`nan` rows. Halo zoom parameters (offsets, extents, seeds) come from `COZMIC1-files/zoom-key.dat`; template comes from `COZMIC1-files/template-music.conf`; default white-noise file is `COZMIC1-files/wnoise_uc_14354454_1024-001.dat`. Output is written to `configs/music_<halo_name>_<transfer_stem>.conf`.

## 8. Run MUSIC to generate initial conditions

```bash
./run_music.sh Halo004                                                           # single config (errors if >1 found)
./run_music.sh Halo004 --all                                                     # all configs for Halo004 in configs/
./run_music.sh Halo004 --all --config-files-dir configs                          # explicit config directory
./run_music.sh Halo004 --all --music-exe /path/to/MUSIC                          # custom MUSIC executable
```

`halo_name` is required. Without `--all`, runs the single config matching `configs/music_<halo_name>_*.conf` (errors if more than one match). With `--all`, runs all matching configs in `--config-files-dir` (default: `configs/`). Default MUSIC executable: `$MUSIC_EXE` env var or `../MUSIC2/build/MUSIC`.
