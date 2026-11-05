#!/usr/bin/env python3
"""Non-flight verification; records actual nonzero test counts."""
import argparse
import json
import re
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);out=p.parse_args().output.resolve()
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[3]
    subprocess.run([sys.executable,str(repo/'research/sta-rate-control/scripts/verify_m08.py'),
                    '--output',str(out/'regression')],cwd=repo,check=True)
    generated=(repo/'build/px4_sitl_default/msg/topics_sources/sta_rate_ctrl_status.cpp').read_text()
    fields=re.search(r'__orb_sta_rate_ctrl_status_fields\[\] = "([^"]+)"',generated)
    assert fields is not None, 'Missing generated format'
    format_len=len('sta_rate_ctrl_status:')+len(fields.group(1))
    assert format_len < 1500, f'PX4 logger refuses format length {format_len}'
    xml=out/'ControlDecimation.xml'
    with (out/'ControlDecimation.log').open('w') as stream:
        r=subprocess.run([str(repo/'build/px4_sitl_test/unit-ControlDecimation'),'--gtest_output=xml:'+str(xml)],
                         stdout=stream,stderr=subprocess.STDOUT,cwd=repo)
    attrs=ET.parse(xml).getroot().attrib
    assert r.returncode==0 and int(attrs['tests'])>=10 and all(int(attrs[k])==0 for k in ('failures','errors','disabled')),attrs
    e=json.loads((out/'regression/evidence.json').read_text());e['tests']['ControlDecimation']={k:int(attrs[k]) for k in ('tests','failures','errors','disabled')}
    e['logger_format_length']=format_len
    e['commands'].append(dict(name='ControlDecimation',returncode=r.returncode))
    (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    print('M09 actual C++:',sum(x['tests'] for k,x in e['tests'].items() if not k.startswith('python')))


if __name__=='__main__':main()
