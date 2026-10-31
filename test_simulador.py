import unittest
from simulador import FileSystem, FSError

class TestFileSystem(unittest.TestCase):
    def test_tree_and_relative(self):
        fs = FileSystem()
        fs.mkdir('/home')
        fs.cd('/home')
        fs.create('doc.txt', 10240)
        self.assertIn('doc.txt', fs.tree())
        self.assertEqual(fs.normalize('../home/doc.txt'), '/home/doc.txt')
        self.assertEqual(fs.nodes['/home/doc.txt']['blocks'], [1, 2, 3])
        self.assertEqual(fs.nodes['/home/doc.txt']['index'], 0)
        self.assertIn('2048 B', fs.status())

    def test_crud_and_move(self):
        fs = FileSystem()
        fs.mkdir('/a')
        fs.create('/a/f', content='abc')
        self.assertEqual(fs.read('/a/f'), 'abc')
        fs.update('/a/f', content='novo')
        self.assertEqual(fs.read('/a/f'), 'novo')
        fs.move('/a/f', '/a/g')
        fs.delete('/a/g')
        self.assertEqual(fs.disk.count(None), fs.blocks)

    def test_fragmentation_and_compact(self):
        fs = FileSystem(blocks=8, block_size=4, strategy='contiguous')
        for name in ('a','b','c'):
            fs.create('/'+name, 8)
        fs.delete('/b')
        self.assertIn('SIM', fs.status())
        with self.assertRaises(FSError):
            fs.create('/d', 12)
        fs.compact()
        fs.create('/d', 12)
        self.assertEqual(fs.nodes['/d']['blocks'], [4, 5, 6])

    def test_recursive(self):
        fs = FileSystem()
        fs.mkdir('/a')
        fs.create('/a/f', 2)
        with self.assertRaises(FSError):
            fs.delete('/a')
        fs.delete('/a', recursive=True)
        self.assertNotIn('/a', fs.nodes)

if __name__ == '__main__':
    unittest.main()
