import os, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db import init_db, conn
from app.monitors.lifes import LifesMonitor
from app.monitors.etre import EtreMonitor
from app.service import run_monitor

templates = Jinja2Templates(directory="app/templates")
scheduler = AsyncIOScheduler()

async def run_all():
    await run_monitor(LifesMonitor())
    await run_monitor(EtreMonitor())

@asynccontextmanager
async def lifespan(app):
    init_db()
    minutes = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))
    scheduler.add_job(run_all, "interval", minutes=minutes, id="all", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="日本购物网站库存监控", lifespan=lifespan)

@app.get("/")
def dashboard(request: Request):
    with conn() as c:
        sites = c.execute("""
        SELECT p.site, COUNT(DISTINCT p.id) products,
        SUM(CASE WHEN v.status='out_of_stock' THEN 1 ELSE 0 END) out_count,
        MAX(v.last_checked) last_checked
        FROM products p LEFT JOIN variants v ON v.product_id=p.id
        GROUP BY p.site ORDER BY p.site
        """).fetchall()
        changes = c.execute("""
        SELECT ch.*,p.site,p.name,p.url,p.image_url
        FROM changes ch JOIN products p ON p.id=ch.product_id
        ORDER BY ch.detected_at DESC LIMIT 100
        """).fetchall()
        runs = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 20").fetchall()
    return templates.TemplateResponse("dashboard.html", {"request":request,"sites":sites,"changes":changes,"runs":runs})

@app.post("/run")
async def manual_run(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_all)
    return RedirectResponse("/", status_code=303)

@app.get("/products")
def products(request: Request, site: str = ""):
    with conn() as c:
        q = """SELECT p.*, COUNT(v.id) variants,
        SUM(CASE WHEN v.status='out_of_stock' THEN 1 ELSE 0 END) out_count,
        MAX(v.last_checked) last_checked
        FROM products p LEFT JOIN variants v ON v.product_id=p.id"""
        args=[]
        if site:
            q += " WHERE p.site=?"; args=[site]
        q += " GROUP BY p.id ORDER BY p.last_seen DESC"
        rows=c.execute(q,args).fetchall()
    return templates.TemplateResponse("products.html", {"request":request,"rows":rows,"site":site})

@app.get("/product/{pid}")
def product(request: Request, pid: int):
    with conn() as c:
        p=c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
        vs=c.execute("SELECT * FROM variants WHERE product_id=? ORDER BY color,size",(pid,)).fetchall()
        cs=c.execute("SELECT * FROM changes WHERE product_id=? ORDER BY detected_at DESC",(pid,)).fetchall()
    return templates.TemplateResponse("product.html", {"request":request,"p":p,"variants":vs,"changes":cs})

@app.get("/logs")
def logs(request: Request):
    with conn() as c:
        rows=c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 100").fetchall()
    return templates.TemplateResponse("logs.html", {"request":request,"rows":rows})
