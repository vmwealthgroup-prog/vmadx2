import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from vmadx2_safety import *

class SafetyTests(unittest.TestCase):
    def test_unknown_blocks(self):
        for s in [None, "", "PENDING", "OPEN", "PARTIALLY_FILLED", "unrecognized"]:
            self.assertEqual(retry_decision(s), "BLOCK_AND_RECONCILE")
    def test_cancel_requires_reconcile(self):
        self.assertEqual(retry_decision("CANCELLED"), "RECONCILE_PARTIAL_FILLS_BEFORE_RETRY")
    def test_reconcile(self):
        self.assertEqual(reconcile_quantities({"NFO:x":65},{"NFO:x":30})["NFO:x"]["broker"],30)
        self.assertTrue(reconcile_quantities({}, {"NFO:x":65}))
        self.assertFalse(reconcile_quantities({"x":0},{}))
    def test_freshness(self):
        now=datetime(2026,11,20,10,tzinfo=IST)
        self.assertFalse(freshness(now-timedelta(seconds=91),now).passed)
        self.assertFalse(freshness(now+timedelta(seconds=1),now).passed)
        self.assertTrue(freshness(now,now).passed)
    def test_naive_blocks(self):
        now=datetime(2026,11,20,10)
        self.assertFalse(freshness(now,now).passed)
    def test_prices(self):
        self.assertEqual(limit_price(100,2,0.05,"BUY"),102)
        self.assertEqual(limit_price(100,2,0.05,"SELL"),98)
        with self.assertRaises(ValueError): limit_price(100,21,.05,"BUY")
    def test_empty_gate(self):
        self.assertFalse(may_arm([]))
    def test_gate(self):
        self.assertFalse(may_arm([Check("x",False,"blocked")]))
        self.assertTrue(may_arm([Check("x",True,"verified")]))

if __name__ == "__main__": unittest.main()
