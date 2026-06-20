from cutover import db
from cutover.db import query_value

with db.legacy_conn() as conn:
    print("legacy OK")
    print("tables:", query_value(conn, "SELECT count(*) FROM legacy.tax_master"))