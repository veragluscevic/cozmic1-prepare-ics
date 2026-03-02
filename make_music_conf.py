#!/usr/bin/env python3
"""Generate MUSIC configuration file(s) for a zoom-in halo.

Reads halo-specific parameters (ref_offset, ref_extent, seeds) from a
zoom-key file and substitutes them into a template config, along with the
specified transfer-function and white-noise filenames.

Usage
-----
    # Single transfer file
    python make_music_conf.py <halo_name> <transfer_file> \
        [--wnoise-file FILE] [--template TEMPLATE] [--keyfile KEYFILE]

    # All non-done entries from sim-table.dat
    python make_music_conf.py <halo_name> --all-sim-table-transfers <transfer_directory> \
        [--sim-table SIM_TABLE] [--wnoise-file FILE] [--template TEMPLATE] [--keyfile KEYFILE]

Output file(s) are written to configs/music_<halo_name>_<transfer_stem>.conf
"""

import argparse
import os
import re
import sys


def parse_keyfile(path):
    """Return a dict mapping halo name -> dict of zoom parameters."""
    halos = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 10:
                print(f"Warning: skipping malformed line in {path}: {line}",
                      file=sys.stderr)
                continue
            name = parts[0]
            halos[name] = {
                "ref_offset": f"{parts[1]}, {parts[2]}, {parts[3]}",
                "ref_extent": f"{parts[4]}, {parts[5]}, {parts[6]}",
                "seed11": parts[7],
                "seed12": parts[8],
                "seed13": parts[9],
            }
    return halos


KEY_SECTIONS = {
    "ref_offset": "setup",
    "ref_extent": "setup",
    "transfer_file": "cosmology",
    "seed[10]": "random",
    "seed[11]": "random",
    "seed[12]": "random",
    "seed[13]": "random",
    "filename": "output",
}


def replace_value(lines, key, new_value):
    """Replace the value for 'key'; insert into the correct section if missing."""
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*).*$")
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            lines[i] = m.group(1) + new_value
            return

    new_line = f"{key:16s}= {new_value}"
    section = KEY_SECTIONS.get(key)
    if section is None:
        print(f"Warning: key '{key}' not found and has no known section; "
              "appending to end of file", file=sys.stderr)
        lines.append(new_line)
        return

    section_header = re.compile(rf"^\[{re.escape(section)}\]\s*$")
    next_section = re.compile(r"^\[.+\]\s*$")
    in_section = False
    insert_at = None
    for i, line in enumerate(lines):
        if section_header.match(line):
            in_section = True
            continue
        if in_section:
            if next_section.match(line):
                insert_at = i
                break
            insert_at = i + 1

    if insert_at is None:
        lines.append(f"[{section}]")
        lines.append(new_line)
    else:
        lines.insert(insert_at, new_line)

    print(f"Note: key '{key}' not in template; inserted into [{section}]",
          file=sys.stderr)


def format_mass(mass_str):
    """Match repository filename convention for mass strings."""
    mass_str = mass_str.strip()
    if mass_str == "1":
        return "1e0"
    return mass_str


def clean_sigma(sigma_str):
    """Strip trailing mantissa zeros in scientific notation."""
    s = sigma_str.strip()
    if "e" in s or "E" in s:
        sep = "e" if "e" in s else "E"
        mantissa, exponent = s.split(sep)
        mantissa = mantissa.rstrip("0").rstrip(".")
        return f"{mantissa}e{exponent}"
    return s


def list_non_done_transfer_files(sim_table_path, transfer_dir):
    """Return transfer-file paths for non-done, non-nan entries in sim-table."""
    transfer_paths = []
    missing = []
    with open(sim_table_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            n, m, sigma, _stype, status = parts[:5]
            if status == "done" or sigma.lower() == "nan":
                continue

            mass_fmt = format_mass(m)
            sigma_fmt = clean_sigma(sigma)
            fname = f"camb_n{n}_{mass_fmt}GeV_{sigma_fmt}_tk.dat"
            fpath = os.path.join(transfer_dir, fname)
            if os.path.isfile(fpath):
                transfer_paths.append(fpath)
            else:
                missing.append(fname)
    return transfer_paths, missing


def write_config(transfer_file, halo_name, halo, template_path, wnoise_file, icdir):
    """Create one MUSIC config file and return its output path."""
    with open(template_path) as f:
        lines = [line.rstrip("\n") for line in f]

    transfer_stem = os.path.splitext(os.path.basename(transfer_file))[0]

    replace_value(lines, "ref_offset", halo["ref_offset"])
    replace_value(lines, "ref_extent", halo["ref_extent"])
    replace_value(lines, "transfer_file", transfer_file)
    replace_value(lines, "seed[10]", wnoise_file)
    replace_value(lines, "seed[11]", halo["seed11"])
    replace_value(lines, "seed[12]", halo["seed12"])
    replace_value(lines, "seed[13]", halo["seed13"])
    os.makedirs(icdir, exist_ok=True)
    ic_path = os.path.join(icdir, f"ic_gadget_{halo_name}_{transfer_stem}")
    replace_value(lines, "filename", ic_path)

    out_name = f"music_{halo_name}_{transfer_stem}.conf"
    out_path = os.path.join("configs", out_name)
    os.makedirs("configs", exist_ok=True)
    with open(out_path, "w") as f:
        for line in lines:
            f.write(line + "\n")
    return out_path


def main():
    default_template = "COZMIC1-files/template-music.conf"
    default_keyfile = "COZMIC1-files/zoom-key.dat"
    default_wnoise = "COZMIC1-files/wnoise_uc_14354454_1024-001.dat"

    parser = argparse.ArgumentParser(
        description="Generate MUSIC config file(s) for a zoom-in halo.")
    parser.add_argument("halo_name", help="Halo name as listed in the key file")
    parser.add_argument("transfer_file", nargs="?",
                        help="Single transfer-function file (omit when using --all-sim-table-transfers)")
    parser.add_argument("--all-sim-table-transfers", metavar="DIR", default=None,
                        help="Generate configs for all non-done transfer files found in DIR using sim-table.dat")
    parser.add_argument("--sim-table", default="sim-table.dat",
                        help="Path to sim-table.dat (default: sim-table.dat)")
    parser.add_argument("--wnoise-file", default=default_wnoise,
                        help=f"White-noise filename (seed[10]) (default: {default_wnoise})")
    parser.add_argument("--template", default=default_template,
                        help=f"Template config file (default: {default_template})")
    parser.add_argument("--keyfile", default=default_keyfile,
                        help=f"Zoom-key file (default: {default_keyfile})")
    parser.add_argument("--icdir", default="ic",
                        help="Output directory for ICs (default: ic)")
    args = parser.parse_args()

    # Require exactly one transfer mode.
    if (args.transfer_file is None) == (args.all_sim_table_transfers is None):
        parser.error("provide exactly one of: transfer_file OR --all-sim-table-transfers DIR")

    halos = parse_keyfile(args.keyfile)
    if args.halo_name not in halos:
        sys.exit(f"Error: halo '{args.halo_name}' not found in {args.keyfile}. "
                 f"Available: {', '.join(halos.keys())}")
    halo = halos[args.halo_name]

    if args.transfer_file is not None:
        out_path = write_config(
            args.transfer_file,
            args.halo_name,
            halo,
            args.template,
            args.wnoise_file,
            args.icdir,
        )
        print(f"Wrote {out_path}")
        return

    transfer_paths, missing = list_non_done_transfer_files(
        args.sim_table, args.all_sim_table_transfers
    )
    if not transfer_paths:
        print("No matching non-done transfer files found.")
    for transfer_path in transfer_paths:
        out_path = write_config(
            transfer_path,
            args.halo_name,
            halo,
            args.template,
            args.wnoise_file,
            args.icdir,
        )
        print(f"Wrote {out_path}")

    if missing:
        print(
            f"Skipped {len(missing)} non-done entries from {args.sim_table} "
            f"(transfer file not found in {args.all_sim_table_transfers}).",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
