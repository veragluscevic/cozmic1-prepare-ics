# Key Commands and Instructions

#############
# !!! Key files: sim-table.dat, prepare-transfers.sh !!!
# Key results: converted/
# Before you begin, on the same level as this repo, do:
# git clone git@github.com:kboddy/class_public.git class_dmeff_rui_used 
# git checkout dmeff
# and then make the code in there so you can use that version of CLASS
##############


## 0. sim-table.dat contains the IDM parameters for all planned and done runs. Do NOT change manually. 

## 1. Generate CLASS ini files

```bash
python generate_all_inis_from_sim-table.py
```

Reads `sim-table.dat` and templates (`minimal_syncronous.ini`, `minimal_newtonian.ini`) to create ini files in `inis/`.

## 2. Run CLASS

```bash
bash run_class.sh
```

Runs CLASS on all ini files in `inis/`, saves output to `output/`.

## 3. Convert CLASS to CAMB format

```bash
bash convert_all.sh
```

Converts all CLASS output (sync + newt + background) to CAMB 13-column format in `converted/`.

Single file:

```bash
python class_to_camb.py output/n2_1e-2GeV_1.3e-25_sync_tk.dat output/n2_1e-2GeV_1.3e-25_newt_tk.dat output/n2_1e-2GeV_1.3e-25_sync_background.dat -o converted/camb_n2_1e-2GeV_1.3e-25_tk.dat
```

## 4. Plot transfer functions

```bash
python plot_transfer.py                                # defaults: n=2, m=1e-2
python plot_transfer.py -n 4 -m 1e-4                   # specific (n, m)
python plot_transfer.py -m all --no-midpoint            # all masses, skip midpoint
python plot_transfer.py -m all --no-midpoint -s         # save to plots/
python plot_transfer.py --mwdm 6.5                      # change WDM reference mass
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
./prepare-transfers.sh
```

For each pending (non-`done`) entry in `sim-table.dat`:

1. Generates any missing ini files in `inis/`
2. Runs CLASS for entries with missing output files in `output/`
3. Runs `analyze_pk.py --recalculate-sigma --plot` for each (n, m) pair
4. Converts CLASS output to CAMB format in `converted/` (via `class_to_camb.py`)

## 6. Compare CLASS vs CAMB output

```bash
python plot_test.py --class-file <class_file> --camb-file <camb_file> -i <column_index>
python plot_test.py --class-file <class_file> --camb-file <camb_file> -i 1 -s
```
