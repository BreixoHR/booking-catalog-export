import json
import tempfile
import unittest
from pathlib import Path

from catalog.customer_groups import ADULT, CHILD, INFANT, OTHER, SENIOR, YOUTH, age_range, classify
from catalog.export import to_csv, to_things_to_do
from catalog.http import CallBudgetExceeded, HttpClient
from catalog.model import Price
from catalog.regiondo import RegiondoClient, build_query, sign
from catalog.turitop import TuritopClient

import fake_apis


class CustomerGroupsTest(unittest.TestCase):
    def test_age_ranges(self):
        self.assertEqual(age_range("Niños (6-10)"), (6, 10))
        self.assertEqual(age_range("Adultos (+18)"), (18, None))
        self.assertEqual(age_range("Senior 65+"), (65, None))
        self.assertEqual(age_range("Kinder bis 5 Jahre"), (0, 5))
        self.assertEqual(age_range("Adulto"), (None, None))

    def test_classify(self):
        cases = {
            "Adultos (+18)": ADULT,
            "Niños (6-10)": CHILD,  # la versión anterior lo marcaba como bebé por contener "0"
            "Jóvenes (12-18)": YOUTH,  # y este como adulto por contener "18"
            "Bebé (0-2)": INFANT,
            "Child 4-12": CHILD,
            "Kinder bis 5 Jahre": CHILD,
            "Senior 65+": SENIOR,
            "Estudiante": YOUTH,
            "Entrada general": ADULT,
            "Erwachsene": ADULT,
            "Enfant": CHILD,
            "Audioguía": OTHER,
        }
        for name, group in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify(name), group)


class MoneyTest(unittest.TestCase):
    def test_exact_units_and_nanos(self):
        self.assertEqual(Price("1", "", ADULT, "19.90").money(), {"currency_code": "EUR", "units": "19", "nanos": 900000000})
        self.assertEqual(Price("1", "", ADULT, "25").money(), {"currency_code": "EUR", "units": "25"})
        self.assertEqual(Price("1", "", ADULT, "0,99", "eur").money(), {"currency_code": "EUR", "units": "0", "nanos": 990000000})
        with self.assertRaises(ValueError):
            Price("1", "", ADULT, "gratis").money()


class SigningTest(unittest.TestCase):
    def test_query_is_sorted_and_signature_is_hmac_sha256(self):
        self.assertEqual(build_query({"offset": 0, "limit": 40, "store_locale": "es_ES"}), "limit=40&offset=0&store_locale=es_ES")
        sig = sign("pub", "sec", "a=1", "1700000000000")
        self.assertEqual(len(sig), 64)
        self.assertNotEqual(sig, sign("pub", "sec", "a=2", "1700000000000"))


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.base = fake_apis.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        fake_apis.state.reset()

    def http(self, **kw):
        return HttpClient(self.base, delay_s=0, **kw)

    def test_regiondo_catalog_paginates_and_signs_every_request(self):
        client = RegiondoClient(fake_apis.PUBLIC, fake_apis.SECRET, http=self.http(max_calls=100))
        products = client.catalog()

        self.assertEqual(len(products), 45)
        pages = [r for r in fake_apis.state.requests if r[1] == "/products"]
        self.assertEqual(len(pages), 2, "45 productos con páginas de 40")
        self.assertEqual(client.http.calls, 2 + 45)
        prices = products[0].variations[0].prices
        self.assertEqual([p.group for p in prices], [ADULT, CHILD, INFANT])
        self.assertEqual(prices[0].amount, "19.90")

    def test_regiondo_wrong_secret_fails_fast(self):
        client = RegiondoClient(fake_apis.PUBLIC, "otra", http=self.http())
        with self.assertRaisesRegex(Exception, "401"):
            client.catalog()

    def test_call_budget_stops_the_run(self):
        client = RegiondoClient(fake_apis.PUBLIC, fake_apis.SECRET, http=self.http(max_calls=5))
        with self.assertRaises(CallBudgetExceeded):
            client.catalog()
        self.assertEqual(client.http.calls, 5)

    def test_turitop_grants_refreshes_once_and_normalizes(self):
        client = TuritopClient("M1", fake_apis.SECRET, http=self.http())
        client.tickets("P1")
        fake_apis.state.expire_next = True  # el token caduca entre llamadas
        products = client.catalog(["P1"])

        paths = [r[1] for r in fake_apis.state.requests]
        self.assertEqual(paths.count("/authorization/grant"), 1)
        self.assertEqual(paths.count("/authorization/refresh"), 1)
        prices = products[0].variations[0].prices
        self.assertEqual([p.label for p in prices], ["Adulto", "Niños 4-12"], "ordenadas, sin add-ons y en NFC")
        self.assertEqual([p.group for p in prices], [ADULT, CHILD])

    def test_turitop_bad_credentials(self):
        with self.assertRaisesRegex(Exception, "401"):
            TuritopClient("M1", "mala", http=self.http()).tickets("P1")

    def test_cli_writes_json_csv_and_things_to_do(self):
        import os
        from catalog import __main__ as cli
        from catalog import regiondo

        os.environ["REGIONDO_PUBLIC_KEY"], os.environ["REGIONDO_SECRET"] = fake_apis.PUBLIC, fake_apis.SECRET
        original = regiondo.BASE_URL
        cli.REGIONDO_URL = self.base
        try:
            with tempfile.TemporaryDirectory() as tmp:
                code = cli.main(["regiondo", "--out", tmp, "--ttd-landing", "https://www.example.com/r?p={product_id}&v={variation_id}"])
                self.assertEqual(code, 0)
                catalog = json.loads(Path(tmp, "regiondo_catalog.json").read_text(encoding="utf-8"))
                self.assertEqual(len(catalog), 45)
                csv_lines = Path(tmp, "regiondo_prices.csv").read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(csv_lines), 1 + 45 * 3)
                ttd = json.loads(Path(tmp, "regiondo_things_to_do.json").read_text(encoding="utf-8"))["products"]
                option = ttd[0]["options"][0]
                self.assertEqual(option["landing_page"]["url"], "https://www.example.com/r?p=100&v=500")
                self.assertEqual(option["price_options"][0]["price"], {"currency_code": "EUR", "units": "19", "nanos": 900000000})
        finally:
            cli.REGIONDO_URL = original


class ExportTest(unittest.TestCase):
    def test_csv_escapes_and_things_to_do_skips_unclassified_extras(self):
        from catalog.model import Product, Variation

        p = Product("turitop", "P1", "Tour, con coma", [Variation("V1", "", [
            Price("1", "Adulto", ADULT, "25"),
            Price("2", "Audioguía", OTHER, "5"),
        ])])
        self.assertIn('"Tour, con coma"', to_csv([p]))
        ttd = to_things_to_do([p], "https://x/{product_id}")
        self.assertEqual([po["title"] for po in ttd[0]["options"][0]["price_options"]], ["Adulto"])


if __name__ == "__main__":
    unittest.main()
