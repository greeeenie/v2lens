import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from v2lens.traffic import TrafficMonitor


class GatewayTrafficTests(unittest.TestCase):
    def test_gateway_counters_do_not_merge_or_double_count(self):
        with tempfile.TemporaryDirectory() as folder:
            now=time.time()
            records=[]
            flows=[]
            for gateway,local_port,size in [('tun',50001,100),('socks',50002,200)]:
                records.append(dict(app='Demo.exe',pid=123,path='Demo.exe',protocol='TCP',inbound=gateway,outbound='proxy',
                                    destination='203.0.113.10',port=443,source='172.18.0.1',local_port=local_port,time=now-1))
                flows.append(dict(pid=123,protocol='TCP',local='172.18.0.1',local_port=local_port,
                                  remote='203.0.113.10',remote_port=443,sent=size,received=size*2,last=now))
            data=dict(viewer_pid=os.getpid(),updated=now,status='running',started=now-2,flows=flows)
            (Path(folder)/'traffic.json').write_text(json.dumps(data))
            TrafficMonitor(folder).attach(records)
            self.assertEqual([r['traffic']['sent'] for r in records],[100,200])
            self.assertEqual(sum(r['traffic']['received'] for r in records),600)
