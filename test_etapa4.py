import unittest
from etapa4 import CompleteSystem
from memory_manager import MemoryManager
from simulador import FSError

class MemoryTests(unittest.TestCase):
    def test_compaction(self):
        m=MemoryManager(reserved_kb=4096, dynamic_kb=8, kernel_kb=1024)
        m.create('Disk',512*1024,'critical')
        m.create('Net',1024*1024,'critical')
        m.create('Crypto',512*1024,'critical')
        m.terminate('Net')
        self.assertIn('Compactação: SIM',m.status('reserved'))
        with self.assertRaises(FSError): m.create('Big',1536*1024,'critical')
        m.compact()
        self.assertEqual(m.processes['Crypto'].start,1536*1024)
        m.create('Big',1536*1024,'critical')

    def test_lru_swap(self):
        m=MemoryManager(dynamic_kb=8,page_kb=4)
        m.create('Browser',10240)
        self.assertEqual(len(m.processes['Browser'].pages),3)
        m.translate('Browser',0)
        m.translate('Browser',1)
        m.translate('Browser',0)
        output=m.translate('Browser',2)
        self.assertIn('Vítima:',output)
        self.assertIsNone(m.processes['Browser'].pages[1])
        self.assertEqual(m.faults,3)
        self.assertEqual(m.hits,1)
        self.assertEqual(len(m.swap),1)

    def test_second_chance(self):
        m=MemoryManager(dynamic_kb=8,page_kb=4,algorithm='SECOND_CHANCE')
        m.create('App',12288)
        for page in (0,1,2): m.translate('App',page)
        self.assertEqual(m.faults,3)
        self.assertEqual(sum(x is not None for x in m.frames),2)

    def test_auth_and_previous_stages(self):
        s=CompleteSystem('senha',dynamic_kb=4)
        with self.assertRaises(FSError): s.command('create_process --name Driver --size 512KB --type critical')
        s.command('login --user root --password senha')
        s.command('mkdir /sistema')
        s.command('write_file /sistema/log.txt teste')
        self.assertIn('teste',s.command('read_file /sistema/log.txt'))
        s.command('create_process --name Driver --size 512KB --type critical')
        s.command('create_process --name App --size 10KB --type normal')
        self.assertIn('PAGE FAULT',s.command('translate_address --process App --page 1'))
        self.assertTrue(any(x.operation=='SWAP_IN' for x in s.security.system.history))
        s.command('groupadd devs')
        s.command('useradd carlos --group devs --password abc')
        s.command('logout')
        s.command('login --user carlos --password abc')
        with self.assertRaises(FSError): s.command('memory_compact --reserved')
        with self.assertRaises(FSError): s.command('create_process --name Secret --size 10KB --type critical')

if __name__=='__main__': unittest.main()
