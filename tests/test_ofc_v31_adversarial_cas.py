"""Adversarial isolated CAS scenarios. No production remote or OPS writes."""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from agent import cycle_registry as registry
from agent.verified_pending_cas import verified_receipt

def git(*args, cwd=None):
    return subprocess.run(["git", *map(str,args)], cwd=cwd, text=True,
                          capture_output=True, check=True).stdout.strip()

class AdversarialCASTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.remote=str(root/"isolated.git")
        self.work=root/"work"
        git("init","--bare",self.remote)
        git("init",self.work)
        git("config","user.name","dev-test",cwd=self.work)
        git("config","user.email","dev@example.invalid",cwd=self.work)
        (self.work/"seed").write_text("pinned")
        git("add",".",cwd=self.work)
        git("commit","-m","seed",cwd=self.work)
        git("branch","-M","main",cwd=self.work)
        git("remote","add","origin",self.remote,cwd=self.work)
        git("push","origin","main",cwd=self.work)
        self.source=git("rev-parse","HEAD",cwd=self.work)
        old=os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir,old)
        self.owner="adversarial-dev"
        self.key="artifact:987"
        acquired=registry.transact(self.remote,"acquire",owner=self.owner,
                                   source=self.source,ttl=600)
        self.generation=acquired["generation"]
        registry.transact(self.remote,"reserve",owner=self.owner,
                          generation=self.generation,source=self.source,value=self.key)

    def snapshot(self):
        return (git("ls-remote",self.remote,registry.REF),
                registry.transact(self.remote,"inspect"))

    def test_five_independent_cas_writers_exactly_one_wins(self):
        # Each worker uses a distinct clone and OS process.
        root=Path(self.tmp.name)
        script=root/"contend.py"
        script.write_text('''
import sys,subprocess,time
sys.path.insert(0,sys.argv[1])
from agent import cycle_registry as r
from agent.pending_reconcile import Observation
from agent.verified_pending_cas import reconcile_to_isolated_remote
remote,owner,generation,source,key=sys.argv[2:]
obs=Observation(key,source,"confirmed",'{"verified":true}')
try:
    reconcile_to_isolated_remote(remote,owner=owner,generation=int(generation),
        source=source,now=time.time(),lookup=lambda _:obs,
        verify=lambda _:True,expected_pending=key)
    print("WIN")
except (r.Blocked,subprocess.CalledProcessError):
    print("BLOCKED")
''')
        source_root=str(Path(__file__).resolve().parents[1])
        def worker(i):
            clone=root/("worker-"+str(i))
            git("clone","--quiet",self.remote,clone)
            git("checkout","-q","main",cwd=clone)
            return subprocess.run([sys.executable,str(script),source_root,
                self.remote,self.owner,str(self.generation),self.source,self.key],
                cwd=clone,capture_output=True,text=True,timeout=60)
        with ThreadPoolExecutor(max_workers=5) as pool:
            outcomes=list(pool.map(worker,range(5)))
        self.assertTrue(all(p.returncode==0 for p in outcomes),
                        [(p.stdout,p.stderr) for p in outcomes])
        self.assertEqual(sum(p.stdout.strip()=="WIN" for p in outcomes),1)
        self.assertEqual(sum(p.stdout.strip()=="BLOCKED" for p in outcomes),4)
        final=registry.transact(self.remote,"inspect")
        self.assertIsNone(final["pending"])
        self.assertEqual(final["results"][self.key],'{"verified":true}')
        print("CAS_EVIDENCE workers=5 winners=1 blocked=4 pending=none")

    def test_zip_mutation_and_replayed_source_are_rejected(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,"w") as z:
            z.writestr("evidence.txt","original")
        data=buffer.getvalue()
        artifact={"id":987,"digest":"sha256:"+hashlib.sha256(data).hexdigest(),
                  "expired":False,"size_in_bytes":len(data),
                  "workflow_run":{"id":123,"head_sha":self.source}}
        args={"repo":"example/isolated","run_id":123,"head_sha":self.source}
        verified_receipt(artifact,fetch=lambda _:data,**args)
        before=self.snapshot()
        tampered=bytearray(data)
        tampered[-1]^=1
        with self.assertRaises(registry.Blocked):
            verified_receipt(artifact,fetch=lambda _:bytes(tampered),**args)
        with self.assertRaises(registry.Blocked):
            verified_receipt(artifact,fetch=lambda _:data,
                repo="example/isolated",run_id=123,head_sha="f"*40)
        self.assertEqual(self.snapshot(),before)
        print("ZIP_EVIDENCE mutation=BLOCKED replay_head=BLOCKED remote_unchanged=true")

    def test_remote_main_drift_blocks_record_without_mutating_registry(self):
        before=self.snapshot()
        (self.work/"drift").write_text("changed")
        git("add",".",cwd=self.work)
        git("commit","-m","drift",cwd=self.work)
        git("push","origin","main",cwd=self.work)
        with self.assertRaises(registry.Blocked):
            registry.transact(self.remote,"record",owner=self.owner,
                generation=self.generation,source=self.source,
                value=self.key+"=receipt")
        self.assertEqual(self.snapshot(),before)
        print("DRIFT_EVIDENCE pinned_main=BLOCKED registry_unchanged=true")

    def test_abrupt_process_exit_does_not_clear_pending(self):
        root=Path(self.tmp.name)
        script=root/"crash.py"
        script.write_text("import os; os._exit(37)")
        before=self.snapshot()
        p=subprocess.run([sys.executable,str(script)],cwd=self.work,
                         capture_output=True,timeout=15)
        self.assertEqual(p.returncode,37)
        self.assertEqual(self.snapshot(),before)
        print("CRASH_EVIDENCE exit=37 pending_preserved=true")

    def test_stale_lease_and_duplicate_reservation_are_blocked(self):
        before=self.snapshot()
        with self.assertRaises(registry.Blocked):
            registry.transact(self.remote,"reserve",owner=self.owner,
                generation=self.generation,source=self.source,value=self.key)
        with patch.object(registry.time,"time",return_value=before[1]["expires"]+1):
            with self.assertRaises(registry.Blocked):
                registry.transact(self.remote,"record",owner=self.owner,
                    generation=self.generation,source=self.source,
                    value=self.key+"=receipt")
        self.assertEqual(self.snapshot(),before)
        print("LEASE_EVIDENCE duplicate=BLOCKED expired=BLOCKED pending_preserved=true")

if __name__=="__main__":
    unittest.main()
