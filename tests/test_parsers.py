"""Parser tests — real ss.lv RSS structure + city24 JSON shape (offline, stdlib)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from parsers import parse_city24, parse_sslv  # noqa: E402

SSLV_XML = """<?xml version="1.0" encoding="UTF-8" ?><rss version="2.0"><channel>
<title>t</title>
<item>
 <title><![CDATA[Nice flat in Vecriga]]></title>
 <link>https://www.ss.lv/msg/lv/real-estate/flats/riga/vecriga/bpmih.html</link>
 <description><![CDATA[<a href="x"><img src="y"></a>
 Pagasts: <b>Vecrīga<br>Vecpilsētas 8</b><br/>Iela: <b>Vecpilsētas 8</b><br/>Ist.: <b>5</b><br/>m²: <b>181</b><br/>Stāvs: <b>3/5</b><br/>Sērija: <b>Renov.</b><br/>: <b>2,486 €</b><br/>Cena: <b>450,000  €</b><br/>]]></description>
</item>
<item>
 <title><![CDATA[Rental]]></title>
 <link>https://www.ss.lv/msg/lv/real-estate/flats/riga/mezhciems/cclex.html</link>
 <description><![CDATA[Pagasts: <b><b>Mežciems<br>Druvienas 15A</b></b><br/>Ist.: <b><b>2</b></b><br/>m²: <b><b>49</b></b><br/>Stāvs: <b><b>1/5</b></b><br/>Cena: <b><b>280</b>  €/mēn.</b><br/>]]></description>
</item>
</channel></rss>"""


class SsLvParserTests(unittest.TestCase):
    def test_parses_sale_and_skips_rental(self):
        listings = parse_sslv(SSLV_XML, "Rīga")
        self.assertEqual(len(listings), 1)  # rental item is skipped

    def test_extracts_fields(self):
        lst = parse_sslv(SSLV_XML, "Rīga")[0]
        self.assertEqual(lst.price, 450000.0)
        self.assertEqual(lst.area_m2, 181.0)
        self.assertEqual(lst.rooms, 5)
        self.assertEqual(lst.floor, "3/5")
        self.assertEqual(lst.district, "Vecrīga")
        self.assertEqual(lst.source, "ss.lv")
        self.assertTrue(lst.url.endswith("bpmih.html"))

    def test_price_per_m2_is_computed(self):
        lst = parse_sslv(SSLV_XML, "Rīga")[0]
        self.assertAlmostEqual(lst.price_per_m2, 450000 / 181, places=1)


CITY24 = [
    {
        "id": "2432419", "friendly_id": "3544701", "price": "200900.00",
        "price_per_unit": 2455.99, "property_size": 81.8, "room_count": 4,
        "latitude": 56.93, "longitude": 24.21, "year_built": 2027,
        "address": {"city_name": "Rīga", "district_name": "Pļavnieki",
                    "county_name": None, "parish_name": None, "village_name": None},
        "attributes": {"ENERGY_CERTIFICATE_TYPE": ["A"], "FLOOR": 3, "TOTAL_FLOORS": 6},
    },
    {
        "id": "999", "friendly_id": "888", "price": "150000.00",
        "property_size": 60, "room_count": 3,
        "address": {"city_name": "Liepāja", "district_name": None, "county_name": None,
                    "parish_name": None, "village_name": None},
        "attributes": {},
    },
]


class City24ParserTests(unittest.TestCase):
    def test_filters_to_target_areas(self):
        listings = parse_city24(CITY24, {"Rīga", "Jūrmala", "Mārupe", "Mārupes novads"})
        self.assertEqual(len(listings), 1)  # Liepāja is filtered out

    def test_extracts_fields(self):
        lst = parse_city24(CITY24, {"Rīga"})[0]
        self.assertEqual(lst.price, 200900.0)
        self.assertEqual(lst.area_m2, 81.8)
        self.assertEqual(lst.rooms, 4)
        self.assertEqual(lst.energy_class, "A")
        self.assertEqual(lst.district, "Pļavnieki")
        self.assertEqual(lst.floor, "3/6")
        self.assertEqual(lst.source, "city24")
        self.assertEqual(lst.id, "2432419")


if __name__ == "__main__":
    unittest.main()
