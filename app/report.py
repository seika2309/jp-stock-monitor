from datetime import datetime
from app.db import conn


def generate_report():

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []

    lines.append("# 日本购物网站库存报告")
    lines.append("")
    lines.append(f"更新时间：{now}")
    lines.append("")


    with conn() as c:

        sites = c.execute("""
        SELECT 
            site,
            COUNT(DISTINCT p.id) AS products,
            SUM(
                CASE WHEN v.status='out_of_stock'
                THEN 1 ELSE 0 END
            ) AS out_count
        FROM products p
        LEFT JOIN variants v
        ON p.id=v.product_id
        GROUP BY site
        """).fetchall()


        lines.append("## 库存统计")
        lines.append("")

        for s in sites:
            lines.append(
                f"- {s['site']}：商品 {s['products']} 个，缺货规格 {s['out_count']} 个"
            )


        lines.append("")
        lines.append("## 最近库存变化")
        lines.append("")


        changes = c.execute("""
        SELECT 
            p.site,
            p.name,
            ch.color,
            ch.size,
            ch.old_status,
            ch.new_status,
            ch.detected_at
        FROM changes ch
        JOIN products p
        ON ch.product_id=p.id
        ORDER BY ch.detected_at DESC
        LIMIT 50
        """).fetchall()


        if not changes:
            lines.append("暂无库存变化")

        else:
            for ch in changes:
                lines.append(
                    f"- [{ch['site']}] {ch['name']} "
                    f"{ch['color']} {ch['size']} : "
                    f"{ch['old_status']} → {ch['new_status']}"
                )


    with open("stock_report.md","w",encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    generate_report()
