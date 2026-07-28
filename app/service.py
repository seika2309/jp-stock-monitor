from datetime import datetime
from app.db import conn
from app.models import Product

def now():
    return datetime.now().isoformat(timespec="seconds")

def save_products(site: str, products: list[Product]):
    ts = now()
    with conn() as c:
        for p in products:
            row = c.execute("SELECT id FROM products WHERE url=?", (p.url,)).fetchone()
            if row:
                pid = row["id"]
                c.execute("UPDATE products SET name=?,price=?,image_url=?,last_seen=? WHERE id=?",
                          (p.name,p.price,p.image_url,ts,pid))
            else:
                cur = c.execute("INSERT INTO products(site,url,name,price,image_url,first_seen,last_seen) VALUES(?,?,?,?,?,?,?)",
                                (p.site,p.url,p.name,p.price,p.image_url,ts,ts))
                pid = cur.lastrowid

            for v in p.variants:
                old = c.execute("SELECT status FROM variants WHERE product_id=? AND color=? AND size=?",
                                (pid,v.color,v.size)).fetchone()
                if old:
                    old_status = old["status"]
                    if old_status != v.status:
                        c.execute("INSERT INTO changes(product_id,color,size,old_status,new_status,detected_at) VALUES(?,?,?,?,?,?)",
                                  (pid,v.color,v.size,old_status,v.status,ts))
                    c.execute("UPDATE variants SET status=?,last_checked=? WHERE product_id=? AND color=? AND size=?",
                              (v.status,ts,pid,v.color,v.size))
                else:
                    c.execute("INSERT INTO variants(product_id,color,size,status,last_checked) VALUES(?,?,?,?,?)",
                              (pid,v.color,v.size,v.status,ts))

async def run_monitor(monitor):
    started = now()
    with conn() as c:
        cur = c.execute("INSERT INTO runs(site,started_at,status) VALUES(?,?,?)",
                        (monitor.site,started,"running"))
        run_id = cur.lastrowid
    try:
        products = await monitor.collect()
        save_products(monitor.site, products)
        with conn() as c:
            c.execute("UPDATE runs SET finished_at=?,status=?,product_count=?,message=? WHERE id=?",
                      (now(),"success",len(products),"",run_id))
        return len(products)
    except Exception as e:
        with conn() as c:
            c.execute("UPDATE runs SET finished_at=?,status=?,message=? WHERE id=?",
                      (now(),"failed",str(e)[:500],run_id))
        raise
