#!/usr/bin/env python3
"""CLI regression: python3 test/io/mapped_constant_outputs.py /path/to/mockturtle_exe.

Uses an exhaustive truth-table check of the emitted structural Verilog.  All
artifacts are temporary; the test does not require an external simulator.
"""
import itertools
import pathlib
import re
import subprocess
import sys
import tempfile

LIBRARY = """GATE inv 1 Y=!a; PIN * INV 1 999 1 0 1 0
GATE buf 1 Y=a; PIN * NONINV 1 999 1 0 1 0
GATE nand2 2 Y=!(a*b); PIN * INV 1 999 1 0 1 0
GATE and2 2 Y=a*b; PIN * NONINV 1 999 1 0 1 0
GATE or2 2 Y=a+b; PIN * NONINV 1 999 1 0 1 0
GATE xor2 3 Y=a^b; PIN * UNKNOWN 1 999 1 0 1 0
"""
CONSTANTS = "GATE zero 0 Y=0;\nGATE one 0 Y=1;\n"


def write_aig(path, outputs, gates, num_pis=2):
    # Implicit PIs, followed by binary delta-encoded ANDs.
    data = bytearray(f"aig {num_pis + len(gates)} {num_pis} 0 {len(outputs)} {len(gates)}\n".encode())
    data.extend("".join(f"{lit}\n" for lit in outputs).encode())
    for index, (a, b) in enumerate(gates, num_pis + 1):
        a, b = sorted((a, b), reverse=True)
        for delta in (2 * index - a, a - b):
            while delta >= 128:
                data.append((delta & 127) | 128)
                delta >>= 7
            data.append(delta)
    path.write_bytes(data)


def evaluate(text, inputs):
    values = {"1'b0": False, "1'b1": True, **inputs}
    drivers = {}
    pending = []
    for line in text.splitlines():
        assign = re.fullmatch(r"\s*assign (\w+) = (~?)([\w']+)\s*;", line)
        cell = re.fullmatch(r"\s*(\w+)\s+g\d+\( (.*) \);", line)
        if assign:
            dst, neg, src = assign.groups()
            pending.append((dst, [src], lambda xs, neg=neg: xs[0] ^ bool(neg)))
        elif cell:
            kind, ports = cell.groups()
            ports = dict(re.findall(r"\.(\w+)\s*\(([^)]+)\)", ports))
            dst = ports.pop('Y').strip()
            sources = [ports[k].strip() for k in sorted(ports)]
            functions = {'zero': lambda xs: False, 'one': lambda xs: True,
                         'inv': lambda xs: not xs[0], 'buf': lambda xs: xs[0],
                         'nand2': lambda xs: not all(xs), 'and2': all,
                         'or2': any, 'xor2': lambda xs: xs[0] ^ xs[1]}
            pending.append((dst, sources, functions[kind]))
        elif re.match(r'\s*(input|output|wire)\s*;', line):
            raise AssertionError(f'Empty declaration: {line}')
        elif line.strip() and not re.match(r"\s*(module|input|output|wire|endmodule)\b", line):
            raise AssertionError(f"Unrecognized Verilog: {line}")
    for dst, _, _ in pending:
        assert dst not in drivers and dst not in inputs, f"Multiple drivers: {dst}"
        drivers[dst] = True
    while pending:
        ready = [p for p in pending if all(s in values for s in p[1])]
        assert ready, f"Undriven or cyclic signals: {pending}"
        for dst, sources, func in ready:
            values[dst] = func([values[s] for s in sources])
            pending.remove((dst, sources, func))
    return values


def main():
    binary = str(pathlib.Path(sys.argv[1]).resolve())
    cases = {'zero': ([0], []), 'one': ([1], []),
             'both_duplicate': ([0, 1, 0, 1], []),
             'complemented_pi': ([3], []), 'duplicate_pi': ([2, 2, 3, 3], []),
             'mixed': ([0, 1, 6, 3, 6, 1], [(4, 2)]),
             'normal': ([6, 7], [(4, 2)]),
             'duplicate_gate': ([6] * 12, [(4, 2)])}
    count = 0
    with tempfile.TemporaryDirectory(prefix='mapped-constants-') as tmp:
        root = pathlib.Path(tmp)
        for library_name, constants in [('both', CONSTANTS), ('none', ''),
                                        ('zero_only', CONSTANTS.splitlines(True)[0]),
                                        ('one_only', CONSTANTS.splitlines(True)[1]),
                                        ('no_buffer', CONSTANTS), ('no_buffer_no_constants', '')]:
            lib = root / 'library.genlib'
            lib.write_text(constants + (LIBRARY if 'no_buffer' not in library_name else '\n'.join(line for line in LIBRARY.splitlines() if not line.startswith('GATE buf')) + '\n'))
            all_cases = [(name, outputs, gates, 2) for name, (outputs, gates) in cases.items()]
            all_cases += [('no_pi_zero', [0], [], 0), ('no_pi_one', [1], [], 0),
                          ('no_pi_duplicates', [0, 1, 0, 1], [], 0)]
            for name, outputs, gates, num_pis in all_cases:
                aig, output, script = (root / f for f in ('input.aig', 'mapped.v', 'script.abc'))
                write_aig(aig, outputs, gates, num_pis)
                script.write_text(f'read_genlib -s "{lib}"\nread "{aig}"\nemap -a\nwrite "{output}"\nquit\n')
                if output.exists():
                    output.unlink()
                result = subprocess.run([binary, '-f', str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                assert result.returncode == 0, (library_name, name, result.stdout, result.stderr)
                assert 'ABORT' not in result.stdout + result.stderr
                text = output.read_text()
                assert not re.search(r'assign \w+ = ~', text), text
                if constants and name in ('zero', 'one'):
                    assert re.search(r'\s+(zero|one)\s+g\d+\(', text), text
                if not constants and name in ('zero', 'one'):
                    assert f"assign y0 = 1'b{outputs[0]}" in text, text
                for bits in itertools.product((False, True), repeat=num_pis):
                    literals = {0: False, **{2 * (i + 1): bit for i, bit in enumerate(bits)}}
                    def lit(value):
                        return literals[value & ~1] ^ bool(value & 1)
                    for index, (a, b) in enumerate(gates, num_pis + 1):
                        literals[2 * index] = lit(a) and lit(b)
                    values = evaluate(text, {f'x{i}': bit for i, bit in enumerate(bits)})
                    assert [values[f'y{i}'] for i in range(len(outputs))] == [lit(o) for o in outputs], (library_name, name, bits, text)
                count += 1
    print(f'PASS: {count} mapped CLI cases, exhaustive truth tables')


if __name__ == '__main__':
    main()
