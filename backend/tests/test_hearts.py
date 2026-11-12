import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.hearts import HeartStore, install

class HeartsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'hearts.sqlite3'
    def tearDown(self):self.tmp.cleanup()
    def test_atomic_shared_counter_and_retry_deduplication(self):
        store=HeartStore(self.path);self.assertEqual(store.update()['count'],0)
        ids=[uuid4() for _ in range(20)]
        with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(lambda item:store.update([item]),ids))
        self.assertEqual(HeartStore(self.path).update(ids)['count'],20)
        self.assertEqual(store.update([uuid4(),uuid4()])['count'],22)
    def test_endpoint_clients_share_total_and_validate_input(self):
        app=FastAPI();install(app,self.path);a=TestClient(app);b=TestClient(app);tap=str(uuid4())
        self.assertEqual(a.post('/api/hearts',json={'tap_ids':[tap]}).json()['count'],1)
        self.assertEqual(b.get('/api/hearts').json()['count'],1)
        self.assertEqual(b.post('/api/hearts',json={'tap_ids':[tap]}).json()['count'],1)
        self.assertEqual(b.post('/api/hearts',json={'tap_ids':[str(uuid4()) for _ in range(100)]}).json()['count'],101)
        self.assertEqual(a.post('/api/hearts',json={'tap_ids':['invalid']}).status_code,422)
        self.assertEqual(a.post('/api/hearts',json={'tap_ids':[]}).status_code,422)
