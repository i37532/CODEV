"""PV00 evidence checks. No flight and no historical-result rewriting."""
import argparse
import ctypes
import gzip
import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

from common import CADENCE, HERE, HISTORY, OLD, REPO, ROOT, command, fingerprint, fresh, probe, save, sha
import numerical


def format_length(name, fields):
    # Logger::write_format serializes the entire o_fields, including padding.
    return len((name + ':' + fields).encode('ascii')) + 1


def check_entry():
    entry=json.loads((ROOT/'audit01/entry.json').read_text())
    for path, record in entry['input_files'].items():
        assert Path(path).is_file() and sha(path)==record['sha256'],path
    return entry


def compare_original():
    old=json.loads((HISTORY/'summary.json').read_text())
    new=json.loads((ROOT/'original01/summary.json').read_text())
    assert new['success'] and len(new['rows'])==144
    for a,b in zip(old['rows'],new['rows']):
        assert {k:v for k,v in a.items() if k not in ('trace','trace_sha256')} == {
                k:v for k,v in b.items() if k not in ('trace','trace_sha256')}
        # Compare uncompressed original bytes; gzip headers contain wall-clock mtime.
        with gzip.open(a['trace'],'rb') as f, gzip.open(b['trace'],'rb') as g:
            assert f.read()==g.read(),a['trace']
        for row in (a,b): assert sha(row['trace'])==row['trace_sha256']
    index=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261024/PROBE/replay02/archive_index.json')
    assert sha(index)=='0b6068bcfdd9451dc57bf3a9dbff4e96b5a1accb1c40b69a4b18ad95ef25ece3'
    archive=json.loads(index.read_text())
    for item in archive:
        assert Path(item['path']).stat().st_size==item['bytes'] and sha(item['path'])==item['sha256']
    return dict(identical_trace_payloads=144,old_archive_files=len(archive),
                old_archive_bytes=sum(r['bytes'] for r in archive),summary_sha256=sha(ROOT/'original01/summary.json'),
                cpp_bridge_cases=72,existing_cpp_cases=new['existing_cpp_cases'],python_cases=18,
                complete=new['complete_trajectories'],rejected=new['rejected_trajectories'],updates=new['total_updates'])


def inspect_numeric():
    data=json.loads((ROOT/'numerical01/summary.json').read_text())
    assert data['success'] and len(data['stops'])==12 and len(data['grid'])==122
    verified=0
    for case in data['grid']:
        r=case['input']
        core=probe.Kernel(ROOT/'original01/kernels.so',2,(r['l1'],r['l2'],0.))
        try:
            assert core.reset(r['nu'])
            code,c=core.evaluate(r['s'],0.,r['h'])
            actual=[x if __import__('math').isfinite(x) else str(x) for x in c]
            expected=case['environments'][0]
            assert code==expected['code'] and actual==expected['outputs']
            verified+=1
        finally: core.close()
    proper=[r for r in data['stops'] if r['algorithm']=='proper']
    assert [r['environments'][0]['site'] for r in proper]==[8,8,8,5]
    assert all(r['arithmetic']['narrowed_non_normal']==['next_nu'] for r in proper[:3])
    assert proper[3]['arithmetic']['terms']['s']['kind']=='subnormal_or_round_to_zero'
    assert all(all(v['passes'] for v in r['arithmetic']['residuals']) for r in proper)
    changes=[r['algorithm']+'/'+r['period'] for r in data['stops']
             if r['environments'][0]['code']!=r['environments'][1]['code']]
    return dict(stops_reproduced=12,proper_first_rejection_sites=[8,8,8,5],
                grid_instrumentation_equivalence=verified,ftz_changes=changes,
                explicit_note='FTZ successes have altered arithmetic, not a numerical repair')


def mode_and_format(out):
    exe=out/'selector_audit'
    command(out,'compile_selector',['g++','-std=c++14','-O2','-Wall','-Wextra','-Werror','-pedantic-errors',
            '-I',probe.VELOCITY,HERE/'selector_audit.cpp','-o',exe])
    text=command(out,'selector_tests',[exe])
    assert 'Tests run: 6, passed: 6, failed: 0' in text
    xml=REPO/'build/px4_sitl_default/parameters.xml'
    params={p.attrib['name']:p for p in ET.parse(xml).iter('parameter')}
    names=['MPC_VP_L1_'+a for a in 'XYZ']+['MPC_VP_L2_'+a for a in 'XYZ']
    assert all(name not in params and len(name)<=16 for name in names)
    mode=params['MPC_VC_MODE']
    assert mode.attrib['default']=='0' and mode.findtext('max')=='4'
    formats={}
    for name in ('sta_velocity_ctrl_status','velocity_ctrl_selection'):
        path=REPO/f'build/px4_sitl_default/msg/topics_sources/{name}.cpp'
        fields=re.search(r'__orb_\w+_fields\[\] = "([^"]+)"',path.read_text())[1]
        length=format_length(name,fields)
        queue=re.search(r'ORB_QUEUE_LENGTH = (\d+)',(REPO/f'msg/{name}.msg').read_text())[1]
        assert length<1500 and queue=='8'
        formats[name]=dict(format_bytes_including_topic_nul=length,queue=int(queue),source_sha256=sha(path))
    # Broad read-only search is saved, including task MODE5 != controller MODE5.
    command(out,'mode_search',['rg','-n','MPC_VC_MODE|ProperIsta|MODE.?5|MPC_VP_',
            'src/modules/mc_pos_control','msg','research/sta-velocity-control/regularized_ista',
            'research/sta-velocity-control/regularized_sta'])
    return dict(candidate_velocity_mode=5,admitted=False,selector_tests=6,
                reserved_parameter_names=names,names_available_in_generated_metadata=True,
                formats=formats,parameter_metadata_sha256=sha(xml),
                new_topic_candidate='proper_ista_velocity_status',
                task_mode5_is_separate_namespace=True)


def baseline_assets(out):
    path=REPO/'research/sta-velocity-control/regularized_ista/ri07/gates/FORMAL/frozen.json'
    frozen=json.loads(path.read_text())
    verified={}
    for group in ('assets','external_assets','generated_assets'):
        entries={}
        for relative,expected in frozen[group].items():
            current=Path(relative) if Path(relative).is_absolute() else REPO/relative
            assert current.is_file(),current
            actual=sha(current)
            assert actual==expected,(str(current),expected,actual)
            entries[str(current)]=dict(bytes=current.stat().st_size,sha256=actual)
        save(out/(group+'.json'),entries)
        verified[group]=len(entries)
    eeprom=REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    firmware=REPO/'build/px4_sitl_default/bin/px4'
    assert sha(eeprom)=='06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc'
    assert sha(firmware)=='61944c348f3b8b918f5f666db7f35b6c623bf720caf5178a95bcbfbd1ad3c80a'
    return dict(verified=verified,freeze_file=fingerprint([path]),current=fingerprint([eeprom,firmware]),
                eeprom_note='audit01 mistakenly omitted nonexistent repo/tmp path; corrected closeout check matches RI07 recovery hash, not a fabricated entry check')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    out=fresh(args.output)
    evidence=dict(success=False,flight_qualified=False,new_flights=0,new_seeds=0)
    try:
        entry=check_entry()
        evidence['original']=compare_original()
        evidence['numerical']=inspect_numeric()
        evidence['mode']=mode_and_format(out)
        evidence['baseline']=baseline_assets(out)
        d=json.loads((ROOT/'diagnostic01/summary.json').read_text())
        assert d['success'] and d['complete']==69 and len(d['rows'])==69
        evidence['diagnostic']=dict(count=69,complete=69,updates=d['updates'],
                                    max_residual=max(r['max_residual'] for r in d['rows']),
                                    max_same_input_difference=max(r['max_step'] for r in d['rows']))
        for row in d['rows']:
            assert sha(row['trace'])==row['trace_sha256'] and row['independent_metric_replay']
        source=Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
        source_index=json.loads((REPO/'research/sta-velocity-control/regularized_ista/ri00/results/source_fingerprints.json').read_text())
        for relative,record in source_index.items():
            assert sha(source/relative)==record['sha256'],relative
        evidence['r_source_files_verified']=len(source_index)
        paper=Path('/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I00/run01/sources/2406.16094v1.pdf')
        assert sha(paper)=='9aa4a20ef2a0f562cfad897e18cb8db96cf174fd332592bb2887e19ddafdd73b'
        evidence['sources']=fingerprint([paper,probe.RATE/'ProperIstaRateControl.cpp',probe.RATE/'ProperIstaRateControl.hpp',
                 probe.RATE/'ProperIstaRateControlTest.cpp',OLD/'probe.py',OLD/'kernel_bridge.cpp',CADENCE,
                 REPO/'research/sta-rate-control/ista_redesign/i01/audit.py',
                 source/'matlab/ista/ista_compensated_step.m',source/'matlab/ista/ista_regularized_step.m'])
        evidence['compiler']=command(out,'compiler',['g++','--version'])
        evidence['platform']=command(out,'platform',['uname','-a'])
        evidence['python']=sys.version
        evidence['submodules']=command(out,'submodules',['git','submodule','status','--recursive'])
        assert evidence['submodules']==entry['submodules']
        assert not command(out,'submodule_dirty',['git','submodule','foreach','--quiet','--recursive','git status --porcelain'])
        assert not command(out,'production_diff',['git','diff','HEAD','--',*probe.PRODUCTION_PATHS])
        evidence['preserved_files']=len(entry['input_files'])
        evidence['baseline_branch']=command(out,'baseline_branch',['git','rev-parse','research/ista-velocity-regularized']).strip()
        assert evidence['baseline_branch']==entry['head']
        check_entry()
        evidence['success']=True
    except Exception as e:
        evidence['error']=repr(e)
        raise
    finally:
        save(out/'evidence.json',evidence)


if __name__=='__main__': main()
