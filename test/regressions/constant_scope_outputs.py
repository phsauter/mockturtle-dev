#!/usr/bin/env python3
"""CLI regression: python3 test/regressions/constant_scope_outputs.py /path/to/mockturtle_exe.

Maps scopes whose outputs are all constant with the command shape used by
callers that pass a network name, symbol tables, and emap timing vectors:

    read_genlib -s <library>
    read --ntk-name <name> <aig>
    emap -D <d> -I <arrivals> -O <required> -L <loads> -a
    write <mapped.v>

A scope with several unused primary inputs and only constant outputs used to
abort in the mapped Verilog writer (std::length_error from a negative name
padding length).  Every case must exit cleanly and drive each output with the
expected constant, either through a constant gate or a constant assignment.
"""
import pathlib
import re
import subprocess
import sys
import tempfile

LIBRARY = """GATE inv1 1 O=!a; PIN * INV 1 999 0.9 0.3 0.9 0.3
GATE nand2 2 O=!(a*b); PIN * INV 1 999 1.0 0.2 1.0 0.2
GATE nor2 2 O=!(a+b); PIN * INV 1 999 1.4 0.5 1.4 0.5
GATE and2 3 O=a*b; PIN * NONINV 1 999 1.9 0.3 1.9 0.3
GATE or2 3 O=a+b; PIN * NONINV 1 999 2.4 0.3 2.4 0.3
GATE xor2 5 O=a*!b+!a*b; PIN * UNKNOWN 2 999 1.9 0.5 1.9 0.5
GATE xnor2 5 O=a*b+!a*!b; PIN * UNKNOWN 2 999 2.1 0.5 2.1 0.5
GATE buf1 2 O=a; PIN * NONINV 1 999 1.0 0.0 1.0 0.0
"""
CONSTANTS = "GATE zero 0 O=CONST0;\nGATE one 0 O=CONST1;\n"


def write_aig(path, num_pis, outputs, symbols):
    lines = [f"aig {num_pis} {num_pis} 0 {len(outputs)} 0"]
    lines += [str(literal) for literal in outputs]
    if symbols:
        lines += [f"i{i} pi{i}" for i in range(num_pis)]
        lines += [f"o{i} po{i}" for i in range(len(outputs))]
    path.write_bytes(("\n".join(lines) + "\n").encode())


def driven_constant(text, name, seen=()):
    """Returns the constant value driving `name`, or None.

    A constant reaches an output through a constant gate, a constant
    assignment, or a buffer from another constant-driven signal (outputs that
    share a constant may be driven by one gate and buffered copies)."""
    if name in seen:
        return None
    cell = re.search(r"^\s*(zero|one)\s+\w+\(\s*\.O\s*\(\s*" + re.escape(name) + r"\s*\)\s*\);", text, re.M)
    if cell:
        return cell.group(1) == "one"
    assign = re.search(r"^\s*assign\s+" + re.escape(name) + r"\s*=\s*1'b([01])\s*;", text, re.M)
    if assign:
        return assign.group(1) == "1"
    buffer = re.search(r"^\s*buf1\s+\w+\(\s*\.a\s*\((\w+)\),\s*\.O\s*\(\s*" + re.escape(name) + r"\s*\)\s*\);",
                       text, re.M)
    if buffer:
        return driven_constant(text, buffer.group(1), seen + (name,))
    return None


def check_case(result, mapped, outputs, symbols, constants):
    """Returns a failure description, or None when the case passed."""
    if result.returncode != 0:
        return f"exit {result.returncode}: {result.stderr.strip()}"
    if "ABORT" in result.stdout + result.stderr or "MAPPED network" not in result.stdout:
        return f"mapping did not complete:\n{result.stdout}{result.stderr}"
    if not mapped.exists():
        return "no mapped Verilog written"
    text = mapped.read_text()
    if "engine3_mapped_constant_scope" not in text:
        return f"network name missing:\n{text}"
    if re.search(r"^\s*(input|output|wire)\s*;", text, re.M):
        return f"empty declaration:\n{text}"
    if re.search(r"assign\s+\w+\s*=\s*~", text):
        return f"complemented assignment:\n{text}"
    for index, literal in enumerate(outputs):
        name = f"po{index}" if symbols else f"y{index}"
        value = driven_constant(text, name)
        if value != bool(literal):
            return f"{name} not driven by constant {literal}:\n{text}"
        if constants and re.search(r"assign\s+" + name + r"\b", text):
            return f"{name} assigned although the library has constant gates:\n{text}"
    return None


def main():
    binary = str(pathlib.Path(sys.argv[1]).resolve())
    count = 0
    failures = []
    with tempfile.TemporaryDirectory(prefix="constant-scope-") as tmp:
        root = pathlib.Path(tmp)
        for library_name, constants in (("constants", CONSTANTS), ("no_constants", "")):
            library = root / f"{library_name}.genlib"
            library.write_text(LIBRARY + constants)
            for num_pis in (0, 1, 2, 9, 10, 11):
                for outputs in ([1], [0], [0, 1], [1] * 11):
                    for symbols in (True, False):
                        for timing in (True, False):
                            aig = root / "scope.aig"
                            mapped = root / "mapped.v"
                            script = root / "script.abc"
                            write_aig(aig, num_pis, outputs, symbols)
                            if mapped.exists():
                                mapped.unlink()
                            emap = "emap -a"
                            if timing:
                                arrivals = ",".join(["0"] * num_pis)
                                required = ",".join(["1.25"] * len(outputs))
                                loads = ",".join(["1"] * len(outputs))
                                emap = "emap -D 1.25" + (f" -I {arrivals}" if num_pis else "") + f" -O {required} -L {loads} -a"
                            script.write_text(
                                f'read_genlib -s "{library}"\n'
                                f'read --ntk-name "engine3_mapped_constant_scope" "{aig}"\n'
                                "print_stats\n"
                                f"{emap}\n"
                                "print_stats\n"
                                f'write "{mapped}"\n'
                                "quit\n")
                            case = (library_name, num_pis, outputs, symbols, timing)
                            result = subprocess.run([binary, "-f", str(script)], stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE, universal_newlines=True)
                            count += 1
                            error = check_case(result, mapped, outputs, symbols, bool(constants))
                            if error:
                                failures.append((case, error))
    for case, error in failures:
        print(f"FAIL {case}: {error}")
    if failures:
        raise SystemExit(f"{len(failures)} of {count} constant-scope CLI cases failed")
    print(f"PASS: {count} constant-scope CLI cases")


if __name__ == "__main__":
    main()
