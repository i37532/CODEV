"""Read-only entry capture plus recoverable old-firmware archive, never flight."""
import argparse
import shutil
from common import *

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not args.execute: print('PV01 offline entry capture; no flight');return
    out=fresh(args.output)
    result={}
    for name,cmd in [('head',['git','rev-parse','HEAD']),('branch',['git','branch','--show-current']),
        ('status',['git','status','--short']),('submodules',['git','submodule','status','--recursive']),
        ('submodule_dirty',['git','submodule','foreach','--quiet','--recursive','git status --porcelain']),
        ('environment',['bash','-c','uname -a; g++ --version; cmake --version; ninja --version; python3 --version'])]:
        result[name]=run(out,name,cmd)
    assert result['head'].strip()==BASE and result['branch'].strip()=='research/proper-ista-velocity'
    assert not result['submodule_dirty'] and len(result['submodules'].splitlines())==33
    assert all(x.startswith(' ') for x in result['submodules'].splitlines())
    paths=[REPO/'research/sta-velocity-control/README_CN.md',
        REPO/'research/sta-velocity-control/regularized_ista/README_CN.md',
        REPO/'research/sta-velocity-control/regularized_ista/USAGE_CN.md',
        REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016']
    paths+=list((REPO/'research/sta-velocity-control/regularized_ista/ri06/results/plots01').rglob('*'))
    paths+=list((HERE.parent/'plan/v1').glob('*.md'))
    # Track unchanged baseline controls/upstream/model inputs separately from new test-only files.
    tracked=run(out,'tracked',['git','ls-files','src','msg','Tools','ROMFS','boards','platforms','.gitmodules'])
    paths += [REPO/x for x in tracked.splitlines() if not x.endswith('PositionControl/CMakeLists.txt')]
    result['preserved_files']=fingerprint(paths)
    old_binary=REPO/'build/px4_sitl_default/bin/px4'
    result['old_firmware']=fingerprint([old_binary])
    shutil.copy2(old_binary,out/'px4.pre_pv01')
    assert sha(out/'px4.pre_pv01')==sha(old_binary)=='61944c348f3b8b918f5f666db7f35b6c623bf720caf5178a95bcbfbd1ad3c80a'
    save(out/'entry.json',result)

if __name__=='__main__':main()
