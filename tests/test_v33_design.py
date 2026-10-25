import unittest
from web.design import escape, LABELS, COLORS


class DesignTests(unittest.TestCase):
    def test_untrusted_labels_are_escaped(self):
        self.assertEqual(escape('<script>"'), '&lt;script&gt;&quot;')

    def test_all_semantic_states_have_distinct_labels(self):
        self.assertEqual(set(LABELS), set(COLORS))
        self.assertEqual(len(set(LABELS.values())), 7)
