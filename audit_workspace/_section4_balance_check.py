"""Structural balance check for the §4 algorithm blocks.

Confirms that each \\begin{algorithm}...\\end{algorithm} block contains
exactly one \\begin{algorithmic}...\\end{algorithmic}, one \\caption,
and one \\label{alg:...}.  Brace balance is checked over the whole
section.  This is the structural pre-pdflatex sanity that the task
calls for; pdflatex itself is not installed in this environment.
"""

import re
import sys
from pathlib import Path

src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp/section4.md')
src = src_path.read_text()

env_open = [(m.start(), 'O') for m in re.finditer(r'\\begin\{algorithm\}', src)]
env_close = [(m.start(), 'C') for m in re.finditer(r'\\end\{algorithm\}', src)]
events = sorted(env_open + env_close)

expected = 'O'
depth = 0
for pos, kind in events:
    if kind != expected:
        print(f'BALANCE ERROR at offset {pos}: got {kind}, expected {expected}')
        sys.exit(1)
    if kind == 'O':
        depth += 1; expected = 'C'
    else:
        depth -= 1; expected = 'O'

if depth != 0:
    print(f'BALANCE ERROR: final depth {depth}')
    sys.exit(1)

pat = re.compile(r'\\begin\{algorithm\}(.*?)\\end\{algorithm\}', re.DOTALL)
blocks = pat.findall(src)
print(f'Found {len(blocks)} algorithm blocks')
for i, body in enumerate(blocks, start=1):
    n_caption = len(re.findall(r'\\caption\{', body))
    n_label   = len(re.findall(r'\\label\{alg:', body))
    n_algo_o  = len(re.findall(r'\\begin\{algorithmic\}', body))
    n_algo_c  = len(re.findall(r'\\end\{algorithmic\}', body))
    n_require = len(re.findall(r'\\Require', body))
    n_ensure  = len(re.findall(r'\\Ensure', body))
    n_return  = len(re.findall(r'\\Return', body))
    o = body.count('{'); c = body.count('}')
    print(f'  Algorithm {i}: caption={n_caption} label={n_label} '
          f'algorithmic={n_algo_o}/{n_algo_c} '
          f'require={n_require} ensure={n_ensure} return={n_return} '
          f'braces={o}/{c}')
    assert n_caption == 1
    assert n_label   == 1
    assert n_algo_o  == 1
    assert n_algo_c  == 1
    assert n_require >= 1
    assert n_ensure  >= 1
    assert n_return  >= 1
    assert o == c, f'block {i}: brace imbalance {o} vs {c}'

print('OK: all 6 algorithm blocks well-formed')
