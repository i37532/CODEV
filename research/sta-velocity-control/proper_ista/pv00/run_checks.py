"""Record real commands and tests; offline only."""
import argparse
from pathlib import Path
import sys
from common import HERE, ROOT, command, fresh, identity, save

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    out=fresh(args.output)
    save(out/'entry.json',identity(out))
    command(out,'pv00_tests',[sys.executable,'-B',HERE/'test_pv00.py','-v'])
    command(out,'analysis_tests',[sys.executable,'-B',HERE.parents[1]/'proper_ista_probe/test_analysis.py','-v'])
    command(out,'diagnostic_dry_run',[sys.executable,'-B',HERE/'diagnostic.py'])
    command(out,'numerical_dry_run',[sys.executable,'-B',HERE/'numerical.py'])
