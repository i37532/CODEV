import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import formal_package as package

class PackageTests(unittest.TestCase):
    def setup_rows(self):
        selection=json.loads((package.PROTOCOL/'selection.json').read_text())
        jobs=package.build_manifest(selection)
        return jobs,package.empty_outcomes(jobs)
    def test_zero_flights_zero_claim(self):
        jobs,rows=self.setup_rows();r=package.aggregate(jobs,rows)
        self.assertEqual(r['accepted'],0);self.assertFalse(r['complete_manifest_executed']);self.assertFalse(r['majority_condition_met'])
        self.assertTrue(all(not x['inference_available'] for x in r['scenes'].values()))
    def test_manifest_order_failure_and_missing_rejected(self):
        jobs,rows=self.setup_rows()
        for changed in (rows[:-1],[rows[1],rows[0],*rows[2:]]):
            with self.assertRaises(ValueError):package.aggregate(jobs,changed)
        rows[0]['status']='failed';rows[0]['reason']='safety gate'
        self.assertEqual(package.aggregate(jobs,rows)['scenes']['hover']['counts']['0']['failed'],1)
        rows[0]['xy_rmse']=0
        with self.assertRaises(ValueError):package.aggregate(jobs,rows)
    def test_accepted_evidence_hash_job_status_window(self):
        jobs,rows=self.setup_rows()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'metrics.json'
            m=dict(accepted=True,job=jobs[0],diagnostic=dict(seconds=64,error=dict(rmse=[.01,.02,.03])))
            def save():path.write_text(json.dumps(m));rows[0].update(status='accepted',metrics_path=str(path),metrics_sha256=package.digest(path))
            save();values,_=package.outcome_rows(jobs,rows);self.assertAlmostEqual(values[0]['xy_rmse'],.015)
            rows[0]['metrics_sha256']='wrong'
            with self.assertRaises(ValueError):package.outcome_rows(jobs,rows)
            for key,value in [('accepted',False),('job',jobs[1])]:
                old=m[key];m[key]=value;save()
                with self.assertRaises(ValueError):package.outcome_rows(jobs,rows)
                m[key]=old
            m['diagnostic']['seconds']=90;save()
            with self.assertRaises(ValueError):package.outcome_rows(jobs,rows)
    def test_noncommand_failure_blocks_majority(self):
        jobs,rows=self.setup_rows()
        with tempfile.TemporaryDirectory() as folder:
            for j,row in zip(jobs,rows):
                mode=j['mode'];errors=[.005,.005,.03 if mode else .001] if mode else [.02,.02,.001]
                m=dict(accepted=True,job=j,diagnostic=dict(seconds=64,error=dict(rmse=errors),windows={w:dict(error=dict(rmse=errors)) for w in ('first_loop','second_loop')}),position_rmse=[.01]*3,yaw_rmse=.01)
                path=Path(folder)/(j['id']+'.json');path.write_text(json.dumps(m));row.update(status='accepted',metrics_path=str(path),metrics_sha256=package.digest(path))
            r=package.aggregate(jobs,rows)
            self.assertEqual(len(r['numerical_improvement_scenes']),5);self.assertFalse(r['majority_condition_met'])
            for j,row in zip(jobs,rows):
                p=Path(row['metrics_path']);m=json.loads(p.read_text());m['diagnostic']['error']['rmse'][2]=.001
                for w in m['diagnostic']['windows'].values():w['error']['rmse'][2]=.001
                p.write_text(json.dumps(m));row['metrics_sha256']=package.digest(p)
            self.assertTrue(package.aggregate(jobs,rows)['majority_condition_met'])
            rows[-1]=dict(id=jobs[-1]['id'],scene=jobs[-1]['scene'],seed=jobs[-1]['seed'],mode=jobs[-1]['mode'],status='invalid',reason='log rejected')
            self.assertFalse(package.aggregate(jobs,rows)['majority_condition_met'])

    def test_collect_preserves_first_failure_and_unattempted(self):
        jobs,_=self.setup_rows()
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'result.json').write_text(json.dumps(dict(error='data integrity failure')))
            ledger=dict(planned=200,attempts=[dict(attempt=1,job=jobs[0],directory=str(p),status='failed')])
            (p/'ledger.json').write_text(json.dumps(ledger));rows=package.collect(jobs,p)
            self.assertEqual(rows[0]['reason'],'data integrity failure');self.assertEqual(sum(r['status']=='unattempted' for r in rows),199)
            ledger['attempts'].append(dict(attempt=2,job=jobs[1],directory=str(p),status='failed'))
            (p/'ledger.json').write_text(json.dumps(ledger))
            with self.assertRaises(ValueError):package.collect(jobs,p)

if __name__=='__main__':unittest.main(verbosity=2)
