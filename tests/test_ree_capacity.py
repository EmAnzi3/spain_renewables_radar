import unittest

from app.enrichment.ree_capacity import parse_capacity_csv


class REECapacityTests(unittest.TestCase):
    def test_parse_current_multiline_header_layout(self):
        width=68
        h1=[""]*width
        h2=[""]*width
        h3=[""]*width
        row=[""]*width

        h1[0]="Nombre y tensión del nudo"
        h1[1]="Código Subestación"
        h1[2]="Comunidad Autónoma"
        h2[26]="Capacidad de acceso otorgada GEN"
        h2[27]="Capacidad de acceso otorgada ALM"
        h2[33]="Capacidad de acceso solicitada en curso y pendiente resolver GEN"
        h2[34]="Capacidad de acceso solicitada en curso y pendiente resolver ALM"

        row[0]="ABADIANO 220"
        row[1]="50000"
        row[2]="País Vasco"
        row[3]="2"
        row[26]="128"
        row[27]="6"
        row[33]="1.234"
        row[34]="12,5"
        row[35]="780"
        row[36]="538"
        row[52]="0"
        row[53]="25,5"

        text="\n".join(";".join(x) for x in (h1,h2,h3,row))
        records=parse_capacity_csv(
            text,
            snapshot_date="2026-10-01",
            source_url="https://www.ree.es/test.csv",
        )
        self.assertEqual(len(records),1)
        item=records[0]
        self.assertEqual(item.node_name,"ABADIANO 220")
        self.assertEqual(item.substation_code,"50000")
        self.assertEqual(item.ccaa,"País Vasco")
        self.assertEqual(item.granted_gen_mw,128.0)
        self.assertEqual(item.granted_storage_mw,6.0)
        self.assertEqual(item.pending_gen_mw,1234.0)
        self.assertEqual(item.pending_storage_mw,12.5)
        self.assertEqual(item.available_gen_rdt_mpe_mw,25.5)


if __name__=="__main__":
    unittest.main()
