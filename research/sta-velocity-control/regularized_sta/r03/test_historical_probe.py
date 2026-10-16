"""Evidence-integrity tests with temporary synthetic inputs, never real logs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import historical_probe as h


class Evidence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.evidence=self.root/'evidence';self.evidence.mkdir()
        self.sources=tuple(self.root/name for name in ('analyzer.py','targets.py','test_analysis.py','targets_replay.py'))
        for path in self.sources:path.write_text('synthetic source '+path.name)
        self.cases=tuple((label,self.root/label) for label,_ in h.CASES)
        records=[]
        for label,run in self.cases:
            run.mkdir();job={'id':label,'mode':0};self.write(run/'job.json',job)
            self.write(run/'runtime_parameters_start.json',{'P':1.0})
            logs=[]
            for i in range(2):
                path=run/f'log00{i}.ulg';path.write_bytes(('synthetic '+label+str(i)).encode())
                logs.append(dict(archive=str(path),sha256=h.digest(path)))
            self.write(run/'result.json',{'logs':logs})
            inputs=[run/'job.json',run/'result.json',run/'runtime_parameters_start.json',*[Path(log['archive']) for log in logs]]
            fingerprints={str(path):h.digest(path) for path in inputs}
            item=dict(label=label,source_run=str(run),historical_job=job,component_valid=True,
                flight_accepted=False,controller_admission_checked=False,inputs_unchanged=True,
                input_sha256_before=fingerprints,input_sha256_after=dict(fingerprints),components={'count':6400})
            records.append(item);self.write(self.evidence/(label+'.json'),item)
        sources={str(path):h.digest(path) for path in self.sources}
        self.summary=dict(success=True,source_unchanged=True,new_flights=0,flight_accepted=False,
            controller_admission_checked=False,source_sha256_before=sources,source_sha256_after=dict(sources),cases=records)
        self.flush()

    def tearDown(self):self.temp.cleanup()
    def write(self,path,value):path.write_text(json.dumps(value,indent=2))
    def flush(self):self.write(self.evidence/'summary.json',self.summary)
    def verify(self):return h._verify(self.evidence,self.sources,self.cases)
    def update_case(self,index=0):self.write(self.evidence/(self.summary['cases'][index]['label']+'.json'),self.summary['cases'][index]);self.flush()

    def test_complete_read_only_success_and_all41_paths(self):
        before={str(p):h.digest(p) for p in self.root.rglob('*') if p.is_file()}
        result=self.verify();self.assertTrue(result['success']);self.assertEqual(result['cases'],6)
        self.assertFalse(result['flight_accepted']);self.assertFalse(result['controller_admission_checked'])
        self.assertEqual(len(result['fingerprints']),41)
        self.assertEqual(before,{str(p):h.digest(p) for p in self.root.rglob('*') if p.is_file()})

    def test_public_entry_uses_fixed_paths(self):
        with patch.object(h,'_verify',return_value={'probe':True}) as verify:
            self.assertEqual(h.check(),{'probe':True});verify.assert_called_once_with(h.EVIDENCE,h.SOURCES,h.CASES)

    def test_missing_case_file(self):
        (self.evidence/'H_PID.json').unlink()
        with self.assertRaises(FileNotFoundError):self.verify()

    def test_missing_case_count(self):
        self.summary['cases'].pop();self.flush()
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_label(self):
        self.summary['cases'][1]['label']='H_PID';self.flush()
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_label_order(self):
        self.summary['cases'].reverse();self.flush()
        with self.assertRaises(ValueError):self.verify()

    def test_strict_success_and_unchanged_booleans(self):
        for key in ('success','source_unchanged'):
            with self.subTest(key=key):
                self.summary[key]=1;self.flush()
                with self.assertRaises(ValueError):self.verify()
                self.summary[key]=True

    def test_never_claim_flight_or_controller_at_summary(self):
        for key in ('flight_accepted','controller_admission_checked'):
            for value in (True,0,None):
                with self.subTest(key=key,value=value):
                    self.summary[key]=value;self.flush()
                    with self.assertRaises(ValueError):self.verify()
            self.summary[key]=False

    def test_new_flights_exact_integer_zero(self):
        for value in (1,False,0.0,None):
            self.summary['new_flights']=value;self.flush()
            with self.subTest(value=value),self.assertRaises(ValueError):self.verify()

    def test_case_flags_strict(self):
        item=self.summary['cases'][0]
        for key,value in [('component_valid',1),('inputs_unchanged',1),('flight_accepted',True),('controller_admission_checked',True)]:
            old=item[key];item[key]=value;self.update_case()
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
            item[key]=old

    def test_source_first_last_mismatch(self):
        self.summary['source_sha256_after'][str(self.sources[0])]='0'*64;self.flush()
        with self.assertRaises(ValueError):self.verify()

    def test_current_source_drift(self):
        self.sources[0].write_text('changed')
        with self.assertRaises(ValueError):self.verify()

    def test_missing_source_fingerprint(self):
        del self.summary['source_sha256_before'][str(self.sources[0])];self.flush()
        with self.assertRaises(ValueError):self.verify()

    def test_input_first_last_mismatch(self):
        item=self.summary['cases'][0];key=next(iter(item['input_sha256_after']));item['input_sha256_after'][key]='0'*64;self.update_case()
        with self.assertRaises(ValueError):self.verify()

    def test_current_input_content_drift(self):
        (self.cases[0][1]/'log001.ulg').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.verify()

    def test_case_summary_mismatch(self):
        path=self.evidence/'H_PID.json';item=json.loads(path.read_text());item['components']['count']=0;self.write(path,item)
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_fixed_source_directory(self):
        self.summary['cases'][0]['source_run']=str(self.root/'elsewhere');self.update_case()
        with self.assertRaises(ValueError):self.verify()

    def test_missing_components_or_error(self):
        item=self.summary['cases'][0];components=item.pop('components');self.update_case()
        with self.assertRaises(ValueError):self.verify()
        item['components']=components;item['error']='retained failure';self.update_case()
        with self.assertRaises(ValueError):self.verify()

    def test_malformed_sha(self):
        self.summary['source_sha256_before'][str(self.sources[0])]='not-sha';self.flush()
        with self.assertRaises(ValueError):self.verify()

    def test_original_job_mismatch(self):
        self.summary['cases'][0]['historical_job']['mode']=1;self.update_case()
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_json_key_rejected(self):
        (self.evidence/'summary.json').write_text('{"success":true,"success":false}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.verify()

    def test_source_change_during_second_pass_rejected(self):
        real=h.digest;seen=0;target=str(self.sources[0])
        def race(path):
            nonlocal seen
            if str(path)==target:
                seen+=1
                if seen>1:return '0'*64
            return real(path)
        with patch.object(h,'digest',side_effect=race),self.assertRaisesRegex(ValueError,'during verification'):self.verify()


if __name__=='__main__':unittest.main(verbosity=2)
