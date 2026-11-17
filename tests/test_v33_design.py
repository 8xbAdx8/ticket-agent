import unittest
from unittest.mock import patch
from web.design import escape, LABELS, COLORS,table,csv_cell


class DesignTests(unittest.TestCase):
    def test_untrusted_labels_are_escaped(self):
        self.assertEqual(escape('<script>"'), '&lt;script&gt;&quot;')

    def test_all_semantic_states_have_distinct_labels(self):
        self.assertEqual(set(LABELS), set(COLORS))
        self.assertEqual(len(set(LABELS.values())), 7)

    def test_table_filter_and_csv_use_identical_visible_rows(self):
        rows=[{"id":str(i),"name":"T04" if i==4 else "normal"} for i in range(12)]
        with patch("web.design.st.text_input",return_value="T04"),patch("web.design.st.markdown") as html,patch("web.design.st.caption"),patch("web.design.st.download_button") as download:
            table(rows,"test")
            markup=html.call_args.args[0]
            self.assertIn("T04",markup)
            self.assertNotIn("normal",markup)
            csv=download.call_args.args[1].decode("utf-8-sig")
            self.assertEqual(len(csv.splitlines()),2)
            self.assertIn("T04",csv)
            self.assertNotIn("normal",csv)

    def test_table_escapes_untrusted_markup_and_preserves_unknown(self):
        with patch("web.design.st.markdown") as html,patch("web.design.st.caption"),patch("web.design.st.download_button"):
            table([{"name":"<script>bad</script>","value":None}],"test",search=False)
            markup=html.call_args.args[0]
            self.assertIn("&lt;script&gt;",markup)
            self.assertIn("未知",markup)
            self.assertNotIn("<script>",markup)

    def test_csv_does_not_execute_untrusted_formulas(self):
        self.assertEqual(csv_cell("=1+1"),"'=1+1")
        self.assertEqual(csv_cell("G7301"),"G7301")
