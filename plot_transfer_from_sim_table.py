#!/usr/bin/env python
"""
Plot (d_dmeff / d_cdm)^2 for a given (n, m) parameter set.

Reads sigma values from sim-table.dat for halfmode, midpoint, and envelope
types, loads the corresponding transfer function files from output/, and
plots the squared ratio against the CDM reference, alongside a WDM
transfer function for the same particle mass.

Usage:
    python plot_transfer.py -n 2 -m 1e-1
"""

import argparse
import os
import math
import numpy as np
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIM_TABLE = os.path.join(SCRIPT_DIR, "sim-table.dat")
CDM_FILE = os.path.join(SCRIPT_DIR, "COZMIC1-template-files", "CDM_class_sync_tk.dat")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")


def format_sci(val):
    """Format a number in scientific notation matching the filename convention.

    Strips trailing zeros from the mantissa, e.g. 4.2000e-28 -> '4.2e-28',
    9.0e-23 -> '9e-23', 2.6145e-24 -> '2.6145e-24'.
    """
    exp = int(math.floor(math.log10(abs(val))))
    mantissa = round(val / 10**exp, 4)
    return f"{mantissa:g}e{exp}"


def parse_sim_table(filepath, n_target, m_target=None):
    """Return list of entries from sim-table.dat for given n (and optionally m).

    If m_target is None, returns entries for all masses.
    Each entry includes 'm' so callers can group by mass.
    """
    entries = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            n_val = int(parts[0])
            m_val = float(parts[1])
            sigma_str = parts[2]
            stype = parts[3]
            if n_val != n_target:
                continue
            if m_target is not None and not math.isclose(m_val, m_target, rel_tol=1e-6):
                continue
            if sigma_str.lower() == "nan":
                continue
            entries.append({"m": m_val, "type": stype, "sigma": float(sigma_str)})
    return entries


def unique_masses(entries):
    """Return sorted list of unique mass values from entries."""
    seen = []
    for e in entries:
        if not any(math.isclose(e["m"], s, rel_tol=1e-6) for s in seen):
            seen.append(e["m"])
    return sorted(seen)


def build_filename(n, m, sigma):
    return f"n{n}_{format_sci(m)}GeV_{format_sci(sigma)}_sync_tk.dat"


def load_columns(filepath):
    """Load k (col 0), d_cdm (col 3), d_dmeff (col 4) from a transfer file."""
    data = np.loadtxt(filepath)
    return data[:, 0], data[:, 3], data[:, 4]


H = 0.7
OMEGA_MH2 = 0.11711
OMEGA_M = OMEGA_MH2 / H**2
RHOCRIT = 2.775e11                    # Msun/h / (Mpc/h)^3
RHO_M = OMEGA_M * RHOCRIT             # Msun/h / (Mpc/h)^3

WDM_A = 0.0437
WDM_B = -1.188
WDM_NU = 1.049
WDM_THETA = 2.012
WDM_ETA = 0.2463


def transfer_wdm(k, mwdm):
    alpha = WDM_A * (mwdm**WDM_B) * ((OMEGA_MH2 / 0.12)**WDM_ETA) * ((H / 0.6736)**WDM_THETA)
    return (1 + (alpha * k) ** (2 * WDM_NU)) ** (-5.0 / WDM_NU)


def M_k(k):
    """Mass scale associated with wavenumber k [h/Mpc]. Returns M in Msun/h."""
    return 4 * np.pi / 3 * RHO_M * (np.pi / k) ** 3


def main():
    parser = argparse.ArgumentParser(
        description="Plot (d_dmeff / d_cdm)^2 for a given (n, m) parameter set."
    )
    parser.add_argument("-n", type=int, default=2, help="power-law index n (default: 2)")
    parser.add_argument("-m", type=str, default="1e-2",
                        help="DM mass in GeV, or 'all' to show all masses (default: 1e-2)")
    parser.add_argument("--mwdm", type=float, default=5.9, help="WDM mass in keV (default: 5.9)")
    parser.add_argument("--no-midpoint", action="store_true", help="omit the midpoint line")
    parser.add_argument("-s", "--save", action="store_true", help="save figure to plots/")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="directory containing CLASS transfer files (default: output/)")
    args = parser.parse_args()

    output_dir = args.output_dir if args.output_dir else OUTPUT_DIR

    n = args.n
    show_all = args.m.lower() == "all"

    k_cdm, d_cdm, _ = load_columns(CDM_FILE)

    if show_all:
        all_entries = parse_sim_table(SIM_TABLE, n)
        masses = unique_masses(all_entries)
    else:
        m_val = float(args.m)
        all_entries = parse_sim_table(SIM_TABLE, n, m_val)
        masses = unique_masses(all_entries)

    if not all_entries:
        print(f"No entries found in sim-table.dat for n={n}")
        raise SystemExit(1)

    LW = 2.2

    type_ls = {"halfmode": "-", "midpoint": ":", "envelope": "--"}
    fixed_mass_colors = {
        1e-4: "C0", 1e-3: "C1", 1e-2: "C2", 1e-1: "C3", 1.0: "C4",
    }
    mass_colors = {m: fixed_mass_colors.get(m, f"C{i}")
                   for i, m in enumerate(masses)}

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = False

    for m in masses:
        m_entries = [e for e in all_entries if math.isclose(e["m"], m, rel_tol=1e-6)]
        for stype in ["halfmode", "midpoint", "envelope"]:
            if stype == "midpoint" and args.no_midpoint:
                continue
            entry = next((e for e in m_entries if e["type"] == stype), None)
            if entry is None:
                continue

            fname = build_filename(n, m, entry["sigma"])
            fpath = os.path.join(output_dir, fname)
            if not os.path.isfile(fpath):
                print(f"  File not found, skipping: {fname}")
                continue

            k, _, d_dmeff = load_columns(fpath)
            ratio_sq = (d_dmeff / d_cdm) ** 2

            if show_all:
                label = rf"{format_sci(m)} GeV, {stype}"
            else:
                label = rf"{stype} ($\sigma = {format_sci(entry['sigma'])}$)"
            ax.semilogx(k, ratio_sq, color=mass_colors[m], ls=type_ls[stype],
                        lw=LW, label=label)
            plotted = True

    if not plotted:
        print("No transfer function files found for the given parameters.")
        raise SystemExit(1)

    k_plot = np.logspace(np.log10(1), np.log10(k_cdm.max()), 500)
    ax.semilogx(k_plot, transfer_wdm(k_plot, 6.5)**2, color="grey", ls="-",
                lw=1.0, label=r"WDM ($m_\mathrm{wdm} = 6.5$ keV)")
    ax.semilogx(k_plot, transfer_wdm(k_plot, args.mwdm)**2, color="black", ls="-",
                lw=1.0, label=rf"WDM ($m_\mathrm{{wdm}} = {args.mwdm}$ keV)")
    ax.axhline(1, color="black", ls=":", lw=0.8)
    ax.axhline(0.25, color="grey", ls=":", lw=0.8)

    ax.set_xlabel(r"$k$ [h/Mpc]")
    ax.set_ylabel(r"$T^2 / T_{\mathrm{CDM}}^2$")
    if show_all:
        fig_suffix = "all"
    else:
        m_label = format_sci(float(args.m))
        fig_suffix = f"{m_label}GeV"
    ax.text(0.97, 0.88, rf"$n = {n}$", transform=ax.transAxes,
            ha="right", va="top", fontsize=14)
    ax.legend(fontsize="small")
    ax.set_xlim(1, 200)
    ax.set_ylim(0, 1.1)
    ax.grid(True, alpha=0.3)

    def k_from_M(M):
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.pi * (4 * np.pi * RHO_M / (3 * np.asarray(M, dtype=float))) ** (1.0 / 3)
    ax2 = ax.secondary_xaxis("top", functions=(M_k, k_from_M))
    ax2.set_xlabel(r"$M\ [M_\odot/h]$")
    mass_ticks = [1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11]
    ax2.set_xticks(mass_ticks)
    ax2.set_xticklabels([rf"$10^{{{int(np.log10(t))}}}$" for t in mass_ticks])

    plt.tight_layout()

    if args.save:
        plotdir = os.path.join(SCRIPT_DIR, "plots")
        os.makedirs(plotdir, exist_ok=True)
        outfig = os.path.join(plotdir, f"transfer_ratio_n{n}_{fig_suffix}.png")
        fig.savefig(outfig, dpi=150)
        print(f"Saved: {outfig}")
    #plt.show()


if __name__ == "__main__":
    main()
