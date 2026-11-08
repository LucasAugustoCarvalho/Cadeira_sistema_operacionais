import unittest
from etapa2 import IntegratedSystem
from io_subsystem import schedule, SSD, RAID

class TestEtapa2(unittest.TestCase):
    def test_sstf_example(self):
        result = schedule([98,183,37,122,14],53,'SSTF')
        self.assertEqual(result['path'], [53,37,14,98,122,183])
        self.assertEqual(result['movement'],208)

    def test_other_schedulers(self):
        self.assertEqual(schedule([10,20],15,'FCFS')['movement'],15)
        self.assertEqual(schedule([10,20],15,'SCAN',max_track=29)['path'],[15,20,29,10])
        self.assertEqual(schedule([10,20],15,'C-SCAN',max_track=29)['path'],[15,20,29,0,10])

    def test_ssd_wear(self):
        ssd = SSD(4)
        a = ssd.write(1)
        b = ssd.write(1)
        self.assertNotEqual(a,b)
        self.assertEqual(ssd.read(1),b)
        self.assertEqual(sum(ssd.wear),2)

    def test_raid5_recovery(self):
        raid = RAID(5,3,4)
        raid.write_blocks([b'abcd',b'WXYZ',b'1234',b'5678'])
        raid.fail(2)
        self.assertEqual(raid.read_block(1),b'WXYZ')
        self.assertEqual(raid.read_block(2),b'1234')
        self.assertIn('[OK]',raid.rebuild(2))
        self.assertEqual(raid.read_block(1),b'WXYZ')

    def test_raid0_failure(self):
        raid = RAID(0,2,4)
        raid.write_blocks([b'abcd',b'WXYZ'])
        raid.fail(2)
        with self.assertRaises(RuntimeError): raid.read_block(1)

    def test_raid1_failure(self):
        raid = RAID(1,2,4)
        raid.write_blocks([b'abcd'])
        raid.fail(1)
        self.assertEqual(raid.read_block(0),b'abcd')
        raid.rebuild(1)

    def test_integrated_io(self):
        s = IntegratedSystem(blocks=16,block_size=4)
        s.command('mkdir /dados')
        s.command('write_file /dados/f "abcdefgh"')
        self.assertTrue(s.queue)
        self.assertEqual(s.fs.read('/dados/f'),'abcdefgh')
        s.command('read_file /dados/f')
        self.assertIn('Total de movimento',s.command('io_run SSTF'))
        self.assertFalse(s.queue)
        s.command('raid_fail 2')
        self.assertIn('[OK]',s.command('raid_read 2'))
        self.assertIn('[OK]',s.command('raid_rebuild 2'))

if __name__ == '__main__': unittest.main()
