import unittest
from v2lens.web_panel import resized_bounds


class ResizeTests(unittest.TestCase):
    def test_edges_and_corners_keep_opposite_sides_anchored(self):
        expected={
            'left':(120,200,880,700),'right':(100,200,920,700),
            'top':(100,230,900,670),'bottom':(100,200,900,730),
            'top-left':(120,230,880,670),'top-right':(100,230,920,670),
            'bottom-left':(120,200,880,730),'bottom-right':(100,200,920,730)}
        for edge,bounds in expected.items():
            self.assertEqual(resized_bounds((100,200,900,700),(690,450),edge,20,30),bounds)

    def test_minimum_size_preserves_the_far_corner(self):
        self.assertEqual(resized_bounds((100,200,900,700),(690,450),'top-left',5000,5000),(310,450,690,450))
        self.assertEqual(resized_bounds((100,200,900,700),(690,450),'bottom-right',-5000,-5000),(100,200,690,450))
        with self.assertRaises(ValueError):resized_bounds((0,0,900,700),(690,450),'invalid',1,1)
