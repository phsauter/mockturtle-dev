#!/usr/bin/env python3
"""Exhaustive public-CLI regression for cyclic native matching and healthy FA/HA covers."""
import argparse
from pathlib import Path
import re
import subprocess


def encode(value):
    data = bytearray()
    while value > 127:
        data.append((value & 127) | 128)
        value >>= 7
    data.append(value)
    return data


def write_aig(path, gates, outputs):
    data = ("aig %d 4 0 %d %d\n" % (len(gates) + 4, len(outputs), len(gates)) +
            "".join("%d\n" % output for output in outputs)).encode()
    for index, (a, b) in enumerate(gates):
        lhs = 2 * (index + 5)
        data += encode(lhs - max(a, b)) + encode(abs(a - b))
    path.write_bytes(data)


def evaluate(path, functions, pattern, count):
    text = path.read_text()
    values = {"x%d" % i: (pattern >> i) & 1 for i in range(4)}

    def net(name):
        name = name.strip()
        if name in ("1'b0", "1'b1"):
            return int(name[3])
        if name.startswith("~"):
            return 1 ^ net(name[1:])
        return values[name]

    for line in text.splitlines():
        gate = re.match(r"\s*(\w+)\s+g\d+\( (.*) \);", line)
        if gate:
            pins = dict(re.findall(r"\.(\w+)\s*\(([^)]+)\)", gate[2]))
            outputs = [pin for pin, function in functions[gate[1]]]
            inputs = {pin: net(name) for pin, name in pins.items() if pin not in outputs}
            for pin, function in functions[gate[1]]:
                values[pins[pin]] = eval(function, {"__builtins__": {}}, inputs) & 1
        assignment = re.search(r"assign\s+(\w+)\s*=\s*(.*);", line)
        if assignment:
            values[assignment[1]] = net(assignment[2])
    return [net("y%d" % i) for i in range(count)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapper", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    root = args.output_directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    mapper = args.mapper.resolve()
    base = """GATE inv 1 O=!a; PIN * INV 1 999 0.02 0 0.02 0
GATE buf 1 O=a; PIN * NONINV 1 999 0.02 0 0.02 0
GATE nand 2 O=!(a*b); PIN * INV 1 999 0.04 0 0.04 0
GATE and 3 O=a*b; PIN * NONINV 1 999 0.08 0 0.08 0
GATE xor 4 O=a^b; PIN * UNKNOWN 1 999 0.10 0 0.10 0
GATE maj 4 O=a*b+a*c+b*c; PIN * UNKNOWN 1 999 0.10 0 0.10 0
GATE xor3 5 O=a^b^c; PIN * UNKNOWN 1 999 0.14 0 0.14 0
GATE zero 0 O=CONST0;
GATE one 0 O=CONST1;
GATE ao21 3 O=a*b+c; PIN * UNKNOWN 1 999 0.07 0 0.07 0
GATE oa21 3 O=(a+b)*c; PIN * UNKNOWN 1 999 0.07 0 0.07 0
GATE aoi21 3 O=!(a*b+c); PIN * UNKNOWN 1 999 0.07 0 0.07 0
GATE oai21 3 O=!((a+b)*c); PIN * UNKNOWN 1 999 0.07 0 0.07 0
"""
    for name, expression, area, delay in [
            ("nand3", "!(a*b*c)", 2.2, .07), ("nor", "!(a+b)", 2, .05),
            ("nor3", "!(a+b+c)", 2.2, .07), ("aoi211", "!(a*b+c+d)", 3, .08),
            ("ao211", "a*b+c+d", 4, .09), ("aoi22", "!(a*b+c*d)", 3, .08),
            ("ao22", "a*b+c*d", 4, .10), ("oai211", "!((a+b)*c*d)", 3, .08),
            ("oa211", "(a+b)*c*d", 4, .09)]:
        base += "GATE %s %s O=%s; PIN * UNKNOWN 1 999 %s 0 %s 0\n" % (name, area, expression, delay, delay)
    # The dead logic is intentional: its matched cuts create the cyclic
    # native dependency that previously caused the sole PO to be omitted.
    cyclic = [(5,2),(4,3),(13,11),(15,7),(14,6),(19,17),(4,2),
              (15,6),(25,23),(6,2),(28,26),(27,21),(26,20),
              (35,33),(31,21),(39,31),(37,40),(36,41),(45,43)]
    gates = []

    def AND(a, b):
        literal = 2 * (len(gates) + 5)
        gates.append((a, b))
        return literal

    def OR(a, b):
        return AND(a ^ 1, b ^ 1) ^ 1

    def XOR(a, b):
        return OR(AND(a, b ^ 1), AND(a ^ 1, b))

    parity2 = XOR(2, 4)
    parity3 = XOR(parity2, 6)
    carry = OR(AND(2, 4), AND(parity2, 6))
    modes = ["", "-a", "-m", "-a -m", "-m -M 1", "-a -m -M 1", "-m -S 1", "-a -m -S 1"]
    mappings = 0
    comparisons = 0
    for inverted_carry in (False, True):
        for inverted_sum in (False, True):
            library = base
            library += "GATE fa 4 C=%s(a*b+a*c+b*c); PIN * UNKNOWN 1 999 0.10 0 0.10 0\n" % ("!" if inverted_carry else "")
            library += "GATE fa 4 S=%s(a^b^c); PIN * UNKNOWN 1 999 0.14 0 0.14 0\n" % ("!" if inverted_sum else "")
            library += "GATE ha 3 C=a*b; PIN * NONINV 1 999 0.08 0 0.08 0\nGATE ha 3 S=a^b; PIN * UNKNOWN 1 999 0.10 0 0.10 0\n"
            functions = {}
            for name, output, expression in re.findall(r"GATE\s+(\S+)\s+\S+\s+(\w+)\s*=\s*([^;]+);", library):
                expression = expression.replace("CONST0", "0").replace("CONST1", "1").replace("!", "~").replace("*", "&").replace("+", "|")
                functions.setdefault(name, []).append((output, compile(expression, "<synthetic-genlib>", "eval")))
            lib = root / ("library-%d%d.genlib" % (inverted_carry, inverted_sum))
            lib.write_text(library)
            circuits = [("cyclic", cyclic, [41]), ("cyclic-mixed", cyclic, [2, 0, 41, 1, 3]),
                        ("fa", gates, [parity3, carry]),
                        ("ha", gates[:3] + [(2, 4)], [parity2, 16]),
                        ("constants", [], [0, 1, 2, 3]),
                        ("dead-lowest-carry", [(5,6),(11,3),(13,5),(12,4),(13,5),(19,17),(15,8),(21,8)], [0,0,0,21,1,24]),
                        ("dead-lowest-sum", gates[:3] + [(2,4)], [0,1,16,17,2])]
            for name, circuit, outputs in circuits:
                aig = root / (name + ".aig")
                write_aig(aig, circuit, outputs)
                targets = [(mode, .56 if name.startswith("dead-lowest") else 1) for mode in modes]
                if name in ("fa", "ha"):
                    targets += [(mode, .001) for mode in ("", "-a", "-m", "-a -m")]
                for mode_index, (mode, required) in enumerate(targets):
                    identity = "%s-%d%d-%d" % (name, inverted_carry, inverted_sum, mode_index)
                    verilog = root / (identity + ".v")
                    arrivals = "0.1,0,0,0.1" if name.startswith("dead-lowest") else "0.1,0,0.1,0"
                    command = 'read_genlib -s "%s"; read --ntk-name regression "%s"; emap -D %s -I %s -O %s %s; write "%s"' % (lib, aig, required, arrivals, ",".join([str(required)] * len(outputs)), mode, verilog)
                    (root / (identity + ".command")).write_text(command + "\n")
                    repeats = 10 if name.startswith("dead-lowest") and "-m" in mode else 1
                    for repeat in range(repeats):
                        if verilog.exists():
                            verilog.unlink()
                        result = subprocess.run([str(mapper), "-c", command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                        (root / (identity + "-repeat-%02d.log" % repeat)).write_text(result.stdout)
                        assert result.returncode == 0, (identity, repeat, "mapper exit", result.returncode)
                        assert not re.search(r"\[(?:e|error)\]|\bABORT(?:ED)?\b", result.stdout, re.IGNORECASE), (identity, repeat, "mapper error")
                        assert verilog.exists() and verilog.stat().st_size > 0, (identity, repeat, "missing fresh output")
                        for pattern in range(16):
                            values = [0] + [(pattern >> i) & 1 for i in range(4)]
                            for a, b in circuit:
                                values.append((values[a // 2] ^ (a & 1)) & (values[b // 2] ^ (b & 1)))
                            golden = [values[output // 2] ^ (output & 1) for output in outputs]
                            actual = evaluate(verilog, functions, pattern, len(outputs))
                            assert actual == golden, (identity, repeat, pattern, golden, actual)
                            comparisons += 1
                        mappings += 1
                    (root / (identity + ".log")).write_text(result.stdout)
                    assert result.returncode == 0, identity
                    for pattern in range(16):
                        values = [0] + [(pattern >> i) & 1 for i in range(4)]
                        for a, b in circuit:
                            values.append((values[a // 2] ^ (a & 1)) & (values[b // 2] ^ (b & 1)))
                        golden = [values[output // 2] ^ (output & 1) for output in outputs]
                        actual = evaluate(verilog, functions, pattern, len(outputs))
                        assert actual == golden, (identity, pattern, golden, actual)
                    if name in ("fa", "ha") and "-m" in mode and "-S" not in mode:
                        assert re.search(r"\s" + name + r"\s+g\d+", verilog.read_text()), identity + " lost native cover"
                    if name.startswith("cyclic") and "-m" in mode:
                        assert "falling back to single-output" in result.stdout, identity + " missing warning"
                    print("PASS", identity, flush=True)
    print("PASS: %d mappings, %d exhaustive input/output comparisons" % (mappings, comparisons))


if __name__ == "__main__":
    main()
