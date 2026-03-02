#!/usr/bin/env python
"""Analyze IDM transfer functions: find cross sections and compute k_hm.

Primary capability: find the halfmode and envelope cross sections (sigma)
for specified (n, m) by running CLASS and matching against a WDM reference
transfer function.  All ratios use d_cdm from the dedicated CDM reference
file ./COZMIC1-template-files/CDM_class_sync_tk.dat (never from dmeff run outputs).

  - Halfmode sigma: the sigma whose transfer T_IDM = d_dmeff/d_cdm first
    drops to 0.5 at the same k as T_WDM (i.e. k_hm_IDM = k_hm_WDM).
  - Envelope sigma: the boundary sigma where T_IDM(k) <= T_WDM(k) for all k
    just barely holds (tightest upper envelope).

Secondary outcome: compute k_hm for existing transfer function files. k_hm
is the wavenumber where d_dmeff/d_cdm first drops to 0.5 (equivalently,
where T^2/T_CDM^2 = 0.25).

Usage:
    python analyze_pk.py -n 2 -m 1e-2                        # show k_hm
    python analyze_pk.py -m all --save-khm                    # save k_hm
    python analyze_pk.py -n 2 -m 1e-2 --recalculate-sigma           # find sigma
    python analyze_pk.py -n 2 -m 1e-2 --recalculate-sigma --plot    # find & plot
"""

import argparse
import subprocess
import sys
import os
import re
import math
import glob
import tempfile
import numpy as np

from plot_transfer_from_sim_table import (
    SCRIPT_DIR, SIM_TABLE, CDM_FILE, OUTPUT_DIR, H,
    format_sci, parse_sim_table, unique_masses,
    build_filename, load_columns, transfer_wdm,
)

DEFAULT_CLASS_EXE = os.environ.get(
    "CLASS_EXE",
    os.path.join(SCRIPT_DIR, "..", "class_dmeff_rui_used", "class"),
)
TEMPLATE_INI = os.path.join(SCRIPT_DIR, "COZMIC1-template-files", "minimal_syncronous.ini")


# ---------- k_hm computation ----------

def compute_khm(k, d_dmeff, d_cdm, threshold=0.5):
    """Find the smallest k where d_dmeff/d_cdm drops to `threshold`.

    Uses linear interpolation between adjacent grid points.
    Returns None if the ratio never drops below the threshold.
    """
    ratio = d_dmeff / d_cdm
    for i in range(len(ratio) - 1):
        if ratio[i] >= threshold and ratio[i + 1] < threshold:
            k_hm = k[i] + (threshold - ratio[i]) / (ratio[i + 1] - ratio[i]) * (k[i + 1] - k[i])
            return float(k_hm)
    return None


def compute_khm_wdm(mwdm, threshold=0.5):
    """Compute k_hm for WDM analytically (where T_wdm(k) = threshold).

    Returns k_hm in h/Mpc.
    """
    from scipy.optimize import brentq
    f = lambda k: transfer_wdm(k, mwdm) - threshold
    return brentq(f, 0.1, 1e4)


# ---------- CLASS execution ----------

def make_ini_content(n, m, sigma, root_rel):
    """Generate ini file content from the template with specified parameters.

    root_rel is the output root path relative to SCRIPT_DIR (e.g.
    'output/n2_1e-2GeV_1.3e-25_sync_').
    """
    with open(TEMPLATE_INI) as f:
        template = f.read()
    lines = template.split('\n')
    new_lines = []
    for line in lines:
        if line.startswith('root = '):
            new_lines.append(f'root = {root_rel}')
        elif line.startswith('m_dmeff = '):
            new_lines.append(f'm_dmeff = {format_sci(m)}')
        elif line.startswith('sigma_dmeff = '):
            new_lines.append(f'sigma_dmeff = {format_sci(sigma)}')
        elif line.startswith('npow_dmeff = '):
            new_lines.append(f'npow_dmeff = {n}')
        else:
            new_lines.append(line)
    return '\n'.join(new_lines)


def run_class(n, m, sigma, class_exe, keep=False):
    """Run CLASS with given parameters and return (k, d_dmeff).

    Only returns k and d_dmeff; callers should use the CDM reference file
    for d_cdm.

    If keep=True, output files use standard naming and persist; an ini file
    is saved in inis/.
    If keep=False, a temporary ini is used and all output files are cleaned
    up after reading the transfer function.
    """
    m_str = format_sci(m)
    sigma_str = format_sci(sigma)

    if keep:
        root_rel = f"output/n{n}_{m_str}GeV_{sigma_str}_sync_"
        ini_dir = os.path.join(SCRIPT_DIR, "inis")
        os.makedirs(ini_dir, exist_ok=True)
        ini_path = os.path.join(ini_dir, f"n{n}_{m_str}GeV_{sigma_str}_sync.ini")
    else:
        root_rel = f"output/_trial_n{n}_{m_str}_{sigma_str}_"
        fd, ini_path = tempfile.mkstemp(suffix=".ini")
        os.close(fd)

    root_abs = os.path.join(SCRIPT_DIR, root_rel)
    ini_content = make_ini_content(n, m, sigma, root_rel)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(ini_path, 'w') as f:
        f.write(ini_content)

    result = subprocess.run(
        [class_exe, ini_path],
        capture_output=True, text=True,
        cwd=SCRIPT_DIR,
    )

    if result.returncode != 0:
        if not keep and os.path.exists(ini_path):
            os.remove(ini_path)
        for fpath in glob.glob(root_abs + "*"):
            os.remove(fpath)
        output = (result.stdout + result.stderr).strip()
        raise RuntimeError(
            f"CLASS failed for sigma={sigma_str} (exit {result.returncode}):\n"
            + "\n".join(output.splitlines()[-5:])
        )

    tk_file = root_abs + "tk.dat"
    if not os.path.exists(tk_file):
        if not keep and os.path.exists(ini_path):
            os.remove(ini_path)
        for fpath in glob.glob(root_abs + "*"):
            os.remove(fpath)
        raise RuntimeError(f"CLASS did not produce {tk_file}")

    k, _, d_dmeff = load_columns(tk_file)

    if not keep:
        os.remove(ini_path)
        for fpath in glob.glob(root_abs + "*"):
            os.remove(fpath)

    return k, d_dmeff


# ---------- Sigma matching criteria ----------

def check_halfmode(k, d_dmeff, d_cdm, k_hm_wdm, tolerance_frac):
    """Check if transfer matches the halfmode criterion within tolerance.

    Returns (is_good, k_hm).
    """
    k_hm = compute_khm(k, d_dmeff, d_cdm)
    if k_hm is None:
        return False, None
    rel_err = abs(k_hm - k_hm_wdm) / k_hm_wdm
    return rel_err < tolerance_frac, k_hm


def check_envelope(k, d_dmeff, d_cdm, mwdm, envelope_tol=0.03, k_max=200.0):
    """Check if d_dmeff/d_cdm <= T_WDM(k) for all k up to k_max.

    k_max excludes edge artifacts near the CLASS grid boundary.
    Returns (is_satisfied, max_excess).
    """
    mask = k <= k_max
    ratio = d_dmeff[mask] / d_cdm[mask]
    t_wdm = transfer_wdm(k[mask], mwdm)
    max_excess = float(np.max(ratio - t_wdm))
    return max_excess <= envelope_tol, max_excess


# ---------- Bisection searches ----------

def find_halfmode_sigma(n, m, k_hm_wdm, sigma_init, d_cdm_ref, class_exe,
                        tolerance_frac, max_iter=10):
    """Bisect on sigma to find halfmode sigma matching k_hm_WDM.

    d_cdm_ref is the CDM reference transfer from CDM_class_sync_tk.dat.
    Decreasing sigma moves the cutoff to higher k (less suppression).
    Returns (sigma, k_hm).
    """
    print(f"  Searching for halfmode sigma "
          f"(target k_hm = {k_hm_wdm * H:.2f} 1/Mpc)...")

    k, d_dmeff = run_class(n, m, sigma_init, class_exe)
    k_hm = compute_khm(k, d_dmeff, d_cdm_ref)

    if k_hm is not None:
        rel_err = abs(k_hm - k_hm_wdm) / k_hm_wdm
        if rel_err < tolerance_frac:
            print(f"    Initial sigma={format_sci(sigma_init)} already "
                  f"matches (err={rel_err:.1%})")
            return sigma_init, k_hm
        if k_hm > k_hm_wdm:
            sigma_lo, sigma_hi = sigma_init, sigma_init * 10
        else:
            sigma_lo, sigma_hi = sigma_init / 10, sigma_init
    else:
        sigma_lo, sigma_hi = sigma_init / 100, sigma_init

    for _expand in range(5):
        _, dd_lo = run_class(n, m, sigma_lo, class_exe)
        khm_lo = compute_khm(k, dd_lo, d_cdm_ref)
        _, dd_hi = run_class(n, m, sigma_hi, class_exe)
        khm_hi = compute_khm(k, dd_hi, d_cdm_ref)

        lo_ok = (khm_lo is not None and khm_lo > k_hm_wdm)
        hi_ok = (khm_hi is None or khm_hi < k_hm_wdm)

        if lo_ok and hi_ok:
            break
        if not lo_ok:
            sigma_lo /= 10
        if not hi_ok:
            sigma_hi *= 10
    else:
        raise RuntimeError(
            f"Could not bracket halfmode for n={n}, m={format_sci(m)}"
        )

    print(f"    Bisecting: sigma in "
          f"[{format_sci(sigma_lo)}, {format_sci(sigma_hi)}]")

    for it in range(max_iter):
        sigma_mid = math.sqrt(sigma_lo * sigma_hi)
        k, d_dmeff = run_class(n, m, sigma_mid, class_exe)
        k_hm = compute_khm(k, d_dmeff, d_cdm_ref)

        if k_hm is None:
            sigma_hi = sigma_mid
            print(f"    [{it+1}/{max_iter}] sigma={format_sci(sigma_mid)}"
                  f" -> no crossing, narrowing")
            continue

        rel_err = abs(k_hm - k_hm_wdm) / k_hm_wdm
        print(f"    [{it+1}/{max_iter}] sigma={format_sci(sigma_mid)}"
              f" -> k_hm={k_hm * H:.2f} 1/Mpc (err={rel_err:.1%})")

        if rel_err < tolerance_frac:
            return sigma_mid, k_hm

        if k_hm > k_hm_wdm:
            sigma_lo = sigma_mid
        else:
            sigma_hi = sigma_mid

    sigma_final = math.sqrt(sigma_lo * sigma_hi)
    k, d_dmeff = run_class(n, m, sigma_final, class_exe)
    k_hm = compute_khm(k, d_dmeff, d_cdm_ref)
    print(f"    Reached max iterations; best sigma={format_sci(sigma_final)}")
    return sigma_final, k_hm


def find_envelope_sigma(n, m, mwdm, sigma_init, d_cdm_ref, class_exe,
                        envelope_tol=0.03, k_max=200.0, max_iter=10):
    """Find the boundary sigma where T_IDM <= T_WDM just barely holds.

    d_cdm_ref is the CDM reference transfer from CDM_class_sync_tk.dat.
    Searches for the smallest sigma such that the envelope condition is
    satisfied (tightest upper envelope).  Returns (sigma, k_hm).
    """
    print(f"  Searching for envelope sigma...")

    k, d_dmeff = run_class(n, m, sigma_init, class_exe)
    ok, max_excess = check_envelope(k, d_dmeff, d_cdm_ref, mwdm, envelope_tol, k_max)

    if ok:
        sigma_hi = sigma_init
        sigma_lo = sigma_init / 10
        for _ in range(5):
            _, dd_lo = run_class(n, m, sigma_lo, class_exe)
            ok_lo, _ = check_envelope(k, dd_lo, d_cdm_ref, mwdm, envelope_tol, k_max)
            if not ok_lo:
                break
            sigma_lo /= 10
        else:
            print(f"    Warning: envelope satisfied down to "
                  f"sigma={format_sci(sigma_lo)}")
            k_hm = compute_khm(k, dd_lo, d_cdm_ref)
            return sigma_lo, k_hm
    else:
        sigma_lo = sigma_init
        sigma_hi = sigma_init * 10
        for _ in range(5):
            _, dd_hi = run_class(n, m, sigma_hi, class_exe)
            ok_hi, _ = check_envelope(k, dd_hi, d_cdm_ref, mwdm, envelope_tol, k_max)
            if ok_hi:
                break
            sigma_hi *= 10
        else:
            raise RuntimeError(
                f"Could not find satisfying sigma for envelope "
                f"at n={n}, m={format_sci(m)}"
            )

    print(f"    Bisecting: sigma in "
          f"[{format_sci(sigma_lo)}, {format_sci(sigma_hi)}]")

    for it in range(max_iter):
        sigma_mid = math.sqrt(sigma_lo * sigma_hi)
        k, d_dmeff = run_class(n, m, sigma_mid, class_exe)
        ok, max_excess = check_envelope(k, d_dmeff, d_cdm_ref, mwdm, envelope_tol, k_max)

        k_hm = compute_khm(k, d_dmeff, d_cdm_ref)
        khm_str = f"k_hm={k_hm * H:.2f}" if k_hm else "no crossing"

        if ok:
            sigma_hi = sigma_mid
            print(f"    [{it+1}/{max_iter}] sigma={format_sci(sigma_mid)}"
                  f" -> OK ({khm_str})")
        else:
            sigma_lo = sigma_mid
            print(f"    [{it+1}/{max_iter}] sigma={format_sci(sigma_mid)}"
                  f" -> exceeds by {max_excess:.4f} ({khm_str})")

    k, d_dmeff = run_class(n, m, sigma_hi, class_exe)
    k_hm = compute_khm(k, d_dmeff, d_cdm_ref)
    return sigma_hi, k_hm


# ---------- Table I/O ----------

def parse_masses_from_table(filepath, n_target, m_target=None):
    """Return sorted list of unique masses from sim-table.dat for given n.

    Unlike parse_sim_table, includes rows with nan sigma.
    """
    masses = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            if int(parts[0]) != n_target:
                continue
            m = float(parts[1])
            if m_target is not None and not math.isclose(m, m_target, rel_tol=1e-6):
                continue
            if not any(math.isclose(m, s, rel_tol=1e-6) for s in masses):
                masses.append(m)
    return sorted(masses)


def get_current_sigma(n, m, stype):
    """Get current sigma from sim-table.dat for given (n, m, type).

    Returns None if not found or nan.
    """
    with open(SIM_TABLE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            if (int(parts[0]) == n
                    and math.isclose(float(parts[1]), m, rel_tol=1e-6)
                    and parts[3] == stype):
                if parts[2].lower() == "nan":
                    return None
                return float(parts[2])
    return None


def get_current_status(n, m, stype):
    """Get current status from sim-table.dat for given (n, m, type).

    Returns the status string, or None if not found.
    """
    with open(SIM_TABLE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            if (int(parts[0]) == n
                    and math.isclose(float(parts[1]), m, rel_tol=1e-6)
                    and parts[3] == stype):
                return parts[4]
    return None


def update_sim_table(n, m, stype, sigma_new, khm_new):
    """Update sigma and khm for a (n, m, type) row in sim-table.dat."""
    with open(SIM_TABLE) as f:
        lines = f.readlines()

    header_re = re.compile(r"^#\s*n\s+m\s+sigma\s+type\s+status")
    new_lines = []
    updated = False

    for line in lines:
        stripped = line.rstrip("\n")

        if header_re.match(stripped):
            if "khm" not in stripped:
                stripped = stripped + "  khm[1/Mpc]"
            new_lines.append(stripped + "\n")
            continue

        if not stripped.strip() or stripped.strip().startswith("#"):
            new_lines.append(stripped + "\n")
            continue

        parts = stripped.split()
        if len(parts) < 5:
            new_lines.append(stripped + "\n")
            continue

        n_str, m_str, sigma_str, st, status = (
            parts[0], parts[1], parts[2], parts[3], parts[4]
        )

        if (int(n_str) == n
                and math.isclose(float(m_str), m, rel_tol=1e-6)
                and st == stype):
            sigma_fmt = format_sci(sigma_new)
            khm_str = f"{khm_new * H:.2f}" if khm_new is not None else "nan"
            new_lines.append(
                f"   {n_str}  {m_str:>4}  {sigma_fmt:>14}    "
                f"{stype:<8}  {status:<6}  {khm_str}\n"
            )
            updated = True
        else:
            khm_str = parts[5] if len(parts) >= 6 else "nan"
            new_lines.append(
                f"   {n_str}  {m_str:>4}  {sigma_str:>14}    "
                f"{st:<8}  {status:<6}  {khm_str}\n"
            )

    with open(SIM_TABLE, "w") as f:
        f.writelines(new_lines)

    if updated:
        khm_disp = f"{khm_new * H:.2f}" if khm_new is not None else "nan"
        print(f"  Updated {SIM_TABLE}: n={n}, m={format_sci(m)}, "
              f"{stype} -> sigma={format_sci(sigma_new)}, khm={khm_disp}")


def save_khm_to_table(results):
    """Append or update k_hm column in sim-table.dat."""
    with open(SIM_TABLE) as f:
        lines = f.readlines()

    def find_khm(n_val, m_val, sigma_str, stype):
        sigma_file = sigma_str.lower()
        if sigma_file == "nan":
            return None
        sigma_fval = float(sigma_file)
        for r in results:
            if (r["n"] == int(n_val)
                    and math.isclose(r["m"], m_val, rel_tol=1e-6)
                    and math.isclose(r["sigma"], sigma_fval, rel_tol=1e-6)
                    and r["type"] == stype):
                return r["khm"]
        return None

    header_re = re.compile(r"^#\s*n\s+m\s+sigma\s+type\s+status")
    new_lines = []
    for line in lines:
        stripped = line.rstrip("\n")
        if header_re.match(stripped):
            if "khm" not in stripped:
                stripped = stripped + "  khm[1/Mpc]"
            new_lines.append(stripped + "\n")
            continue

        if not stripped.strip() or stripped.strip().startswith("#"):
            new_lines.append(stripped + "\n")
            continue

        parts = stripped.split()
        if len(parts) < 5:
            new_lines.append(stripped + "\n")
            continue

        n_str, m_str, sigma_str, stype, status = (
            parts[0], parts[1], parts[2], parts[3], parts[4]
        )
        matched = find_khm(n_str, float(m_str), sigma_str, stype)
        if matched is not None:
            khm_str = f"{matched * H:.2f}"
        elif sigma_str.lower() == "nan":
            khm_str = "nan"
        elif len(parts) >= 6:
            khm_str = parts[5]
        else:
            khm_str = "nan"

        new_lines.append(
            f"   {n_str}  {m_str:>4}  {sigma_str:>14}    "
            f"{stype:<8}  {status:<6}  {khm_str}\n"
        )

    with open(SIM_TABLE, "w") as f:
        f.writelines(new_lines)
    print(f"Updated {SIM_TABLE}")


# ---------- Sigma-finding workflow ----------

def find_sigma_for_mass(n, m, mwdm, class_exe, tolerance_frac, envelope_tol,
                        k_max, max_iter):
    """Find halfmode and envelope sigma for a single (n, m) pair.

    Checks existing values first; only runs CLASS if the current match
    is not good enough.
    """
    k_hm_wdm = compute_khm_wdm(mwdm)
    _, d_cdm_ref, _ = load_columns(CDM_FILE)
    print(f"\n--- n={n}, m={format_sci(m)} GeV  "
          f"(WDM {mwdm} keV, k_hm_wdm={k_hm_wdm * H:.2f} 1/Mpc) ---")

    for stype in ["halfmode", "envelope"]:
        status = get_current_status(n, m, stype)
        if status == "done":
            print(f"  {stype}: status is 'done', skipping recalculation")
            continue

        sigma_cur = get_current_sigma(n, m, stype)

        if sigma_cur is not None:
            fname = build_filename(n, m, sigma_cur)
            fpath = os.path.join(OUTPUT_DIR, fname)

            if os.path.isfile(fpath):
                k, _, d_dmeff = load_columns(fpath)

                if stype == "halfmode":
                    ok, k_hm = check_halfmode(
                        k, d_dmeff, d_cdm_ref, k_hm_wdm, tolerance_frac
                    )
                    if k_hm is not None:
                        rel_err = abs(k_hm - k_hm_wdm) / k_hm_wdm
                        err_str = f"err={rel_err:.1%}"
                    else:
                        err_str = "no crossing"
                    if ok:
                        print(f"  {stype}: sigma={format_sci(sigma_cur)} "
                              f"OK (k_hm={k_hm * H:.2f} 1/Mpc, "
                              f"{err_str})")
                        continue
                    print(f"  {stype}: sigma={format_sci(sigma_cur)} "
                          f"does NOT match "
                          f"(k_hm={'%.2f' % (k_hm * H) if k_hm else 'none'}"
                          f" vs target {k_hm_wdm * H:.2f}, {err_str})")
                else:
                    ok, max_excess = check_envelope(
                        k, d_dmeff, d_cdm_ref, mwdm, envelope_tol, k_max
                    )
                    if ok:
                        k_hm = compute_khm(k, d_dmeff, d_cdm_ref)
                        khm_disp = (f"k_hm={k_hm * H:.2f}"
                                    if k_hm else "no crossing")
                        print(f"  {stype}: sigma={format_sci(sigma_cur)} "
                              f"OK (envelope satisfied, {khm_disp})")
                        continue
                    print(f"  {stype}: sigma={format_sci(sigma_cur)} "
                          f"does NOT satisfy envelope "
                          f"(max excess={max_excess:.4f})")
            else:
                print(f"  {stype}: file {fname} not found, will run CLASS")
        else:
            print(f"  {stype}: no sigma in table, will search")

        sigma_start = sigma_cur
        if sigma_start is None:
            other = "envelope" if stype == "halfmode" else "halfmode"
            sigma_start = get_current_sigma(n, m, other)
            if sigma_start is None:
                raise RuntimeError(
                    f"No starting sigma for n={n}, m={format_sci(m)}, {stype}"
                )
            if stype == "envelope":
                sigma_start *= 10

        if stype == "halfmode":
            sigma_new, k_hm_new = find_halfmode_sigma(
                n, m, k_hm_wdm, sigma_start, d_cdm_ref, class_exe,
                tolerance_frac, max_iter,
            )
        else:
            sigma_new, k_hm_new = find_envelope_sigma(
                n, m, mwdm, sigma_start, d_cdm_ref, class_exe,
                envelope_tol, k_max, max_iter,
            )

        print(f"  Final: running CLASS with sigma={format_sci(sigma_new)} "
              f"(keeping output)")
        run_class(n, m, sigma_new, class_exe, keep=True)
        update_sim_table(n, m, stype, sigma_new, k_hm_new)


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze IDM transfer functions: "
                    "find cross sections and compute k_hm.",
    )
    parser.add_argument(
        "-n", type=int, default=2,
        help="power-law index n (default: 2)")
    parser.add_argument(
        "-m", type=str, default="1e-2",
        help="DM mass in GeV, or 'all' (default: 1e-2)")
    parser.add_argument(
        "--mwdm", type=float, default=5.9,
        help="WDM mass in keV (default: 5.9)")
    parser.add_argument(
        "--no-midpoint", action="store_true",
        help="skip midpoint entries")
    parser.add_argument(
        "-s", "--save", action="store_true",
        help="save plot figure to plots/")
    parser.add_argument(
        "--save-khm", action="store_true",
        help="write k_hm values into sim-table.dat")
    parser.add_argument(
        "--plot", action="store_true",
        help="call plot_transfer_from_sim_table.py with the same arguments")
    parser.add_argument(
        "--recalculate-sigma", action="store_true",
        help="find halfmode/envelope sigma by running CLASS")
    parser.add_argument(
        "--khm-precision-percent", type=float, default=4,
        help="tolerance for halfmode k_hm matching, in %% (default: 4)")
    parser.add_argument(
        "--envelope-tolerance-percent", type=float, default=3,
        help="max allowed overshoot for envelope condition, in %% (default: 3)")
    parser.add_argument(
        "--class-exe", type=str, default=DEFAULT_CLASS_EXE,
        help="path to CLASS executable "
             f"(default: $CLASS_EXE or {DEFAULT_CLASS_EXE})")
    parser.add_argument(
        "--envelope-kmax", type=float, default=200.0,
        help="max k [h/Mpc] for envelope check (default: 200)")
    parser.add_argument(
        "--max-iter", type=int, default=10,
        help="max bisection iterations for sigma search (default: 10)")

    args = parser.parse_args()
    n = args.n
    show_all = args.m.lower() == "all"
    tolerance_frac = args.khm_precision_percent / 100.0
    k_max = args.envelope_kmax
    envelope_tol = args.envelope_tolerance_percent / 100.0

    # --- Find-sigma workflow (runs CLASS as needed) ---
    if args.recalculate_sigma:
        if not os.path.isfile(args.class_exe):
            print(f"ERROR: CLASS executable not found at {args.class_exe}")
            raise SystemExit(1)

        if show_all:
            masses = parse_masses_from_table(SIM_TABLE, n)
        else:
            masses = parse_masses_from_table(SIM_TABLE, n, float(args.m))

        if not masses:
            print(f"No masses found in {SIM_TABLE} for n={n}")
            raise SystemExit(1)

        for m in masses:
            find_sigma_for_mass(
                n, m, args.mwdm, args.class_exe, tolerance_frac, envelope_tol,
                k_max, args.max_iter,
            )
        print()

    # --- k_hm analysis (always runs) ---
    k_cdm, d_cdm, _ = load_columns(CDM_FILE)
    k_hm_wdm = compute_khm_wdm(args.mwdm)

    if show_all:
        all_entries = parse_sim_table(SIM_TABLE, n)
    else:
        m_val = float(args.m)
        all_entries = parse_sim_table(SIM_TABLE, n, m_val)
    masses = unique_masses(all_entries)

    if not all_entries:
        print(f"No entries found in sim-table.dat for n={n}")
        raise SystemExit(1)

    results = []

    print(f"{'n':>3}  {'m':>6}  {'type':<9}  {'sigma':>14}  "
          f"{'k_hm [1/Mpc]':>14}  {'match':>20}")
    print("-" * 78)

    for m in masses:
        m_entries = [
            e for e in all_entries
            if math.isclose(e["m"], m, rel_tol=1e-6)
        ]
        for stype in ["halfmode", "midpoint", "envelope"]:
            if stype == "midpoint" and args.no_midpoint:
                continue
            entry = next(
                (e for e in m_entries if e["type"] == stype), None
            )
            if entry is None:
                continue

            fname = build_filename(n, m, entry["sigma"])
            fpath = os.path.join(OUTPUT_DIR, fname)
            if not os.path.isfile(fpath):
                print(f"{n:>3}  {format_sci(m):>6}  {stype:<9}  "
                      f"{format_sci(entry['sigma']):>14}  {'(no file)':>14}")
                continue

            k, _, d_dmeff = load_columns(fpath)
            khm = compute_khm(k, d_dmeff, d_cdm)

            khm_str = f"{khm * H:.2f}" if khm is not None else "n/a"

            match_str = ""
            if stype == "halfmode":
                if khm is not None:
                    rel_err = abs(khm - k_hm_wdm) / k_hm_wdm
                    if rel_err < tolerance_frac:
                        match_str = f"ok (err={rel_err:.1%})"
                    else:
                        match_str = f"MISMATCH! (err={rel_err:.1%})"
                else:
                    match_str = "MISMATCH! (no crossing)"
            elif stype == "envelope":
                ok, max_excess = check_envelope(
                    k, d_dmeff, d_cdm, args.mwdm, envelope_tol, k_max
                )
                if ok:
                    match_str = f"ok (excess={max_excess:.4f})"
                else:
                    match_str = f"MISMATCH! (excess={max_excess:.4f})"

            print(f"{n:>3}  {format_sci(m):>6}  {stype:<9}  "
                  f"{format_sci(entry['sigma']):>14}  {khm_str:>14}"
                  f"  {match_str}")

            results.append({
                "n": n,
                "m": m,
                "sigma": entry["sigma"],
                "type": stype,
                "khm": khm,
            })

    print()
    for mwdm in [6.5, args.mwdm]:
        khm_wdm = compute_khm_wdm(mwdm)
        print(f"WDM  m_wdm = {mwdm} keV  -->  "
              f"k_hm = {khm_wdm * H:.2f} [1/Mpc]")

    if args.save_khm:
        save_khm_to_table(results)

    if args.plot:
        cmd = [sys.executable, os.path.join(SCRIPT_DIR, "plot_transfer_from_sim_table.py"),
               "-n", str(n), "-m", args.m,
               "--mwdm", str(args.mwdm), "-s"]
        if args.no_midpoint:
            cmd.append("--no-midpoint")
        subprocess.run(cmd)


if __name__ == "__main__":
    main()
